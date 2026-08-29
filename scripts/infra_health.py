#!/usr/bin/env python3
"""Probe every local-infrastructure service and print a status table.

Backs ``make health``. Database-backed probes reuse the same ``OT_*`` settings
as ``GET /readyz`` (core/config/settings.py); HTTP endpoints match the dev
compose port map (docs/runbooks/infrastructure.md).

Exit code: 0 when every probe succeeds, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from dataclasses import dataclass

from core.config.settings import get_settings


#: (name, url, expected_body_substring | None) — None means "HTTP 200 is enough".
#: Host ports follow the OT_*_HOST_PORT overrides from .env / the environment.
def _host_port(env_var: str, default: str) -> str:
    return os.environ.get(env_var, default)


HTTP_ENDPOINTS: tuple[tuple[str, str, str | None], ...] = (
    ("clickhouse", f"http://127.0.0.1:{_host_port('OT_CLICKHOUSE_HOST_PORT', '8123')}/ping", "Ok."),
    (
        "langfuse-web",
        f"http://127.0.0.1:{_host_port('OT_LANGFUSE_HOST_PORT', '3000')}/api/public/health",
        None,
    ),
    ("mlflow", f"http://127.0.0.1:{_host_port('OT_MLFLOW_HOST_PORT', '5000')}/health", "OK"),
    (
        "prometheus",
        f"http://127.0.0.1:{_host_port('OT_PROMETHEUS_HOST_PORT', '9090')}/-/ready",
        "Prometheus Server is Ready.",
    ),
    ("grafana", f"http://127.0.0.1:{_host_port('OT_GRAFANA_HOST_PORT', '3001')}/api/health", "ok"),
)


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str


def probe_postgres(settings: object) -> None:
    import psycopg

    with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as conn:  # type: ignore[attr-defined]
        conn.execute("SELECT 1")


def probe_redis(settings: object, url: str) -> None:
    import redis

    client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    client.ping()
    client.close()


def probe_minio(settings: object) -> None:
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,  # type: ignore[attr-defined]
        access_key=settings.minio_access_key,  # type: ignore[attr-defined]
        secret_key=settings.minio_secret_key,  # type: ignore[attr-defined]
        secure=settings.minio_secure,  # type: ignore[attr-defined]
    )
    if not client.bucket_exists(settings.minio_readiness_bucket):  # type: ignore[attr-defined]
        raise RuntimeError(f"bucket {settings.minio_readiness_bucket!r} missing")  # type: ignore[attr-defined]


def probe_http(url: str, expected: str | None) -> None:
    with urllib.request.urlopen(url, timeout=3) as response:
        body = response.read().decode("utf-8", errors="replace")
    if response.status != 200:  # unreachable; urlopen raises on non-2xx before this
        raise RuntimeError(f"HTTP {response.status}")
    if expected is not None and expected not in body:
        raise RuntimeError(f"unexpected body: {body[:80]!r}")


def main() -> int:
    settings = get_settings()

    checks: list[tuple[str, object]] = [
        ("postgres", lambda: probe_postgres(settings)),
        ("redis", lambda: probe_redis(settings, settings.redis_url)),
        ("minio", lambda: probe_minio(settings)),
        ("falkordb", lambda: probe_redis(settings, settings.falkordb_url)),
    ]
    for name, url, expected in HTTP_ENDPOINTS:
        checks.append((name, lambda u=url, e=expected: probe_http(u, e)))

    results: list[ProbeResult] = []
    width = max(len(name) for name, _ in checks) + 2
    for name, probe in checks:
        start = time.perf_counter()
        try:
            probe()  # type: ignore[operator]
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(ProbeResult(name, True, f"ok ({latency_ms} ms)"))
        except Exception as exc:
            results.append(ProbeResult(name, False, type(exc).__name__))

    print("\nOpenTrading infrastructure health")
    print("=" * (width + 34))
    for result in results:
        state = "OK  " if result.ok else "FAIL"
        print(f"  {result.name:<{width}} {state}  {result.detail}")
    print("=" * (width + 34))

    failed = [result.name for result in results if not result.ok]
    if failed:
        print(f"{len(failed)} service(s) unhealthy: {', '.join(failed)}")
        print("hint: run `make up` and check `make logs SERVICE=<name>`")
        return 1
    print("all services healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
