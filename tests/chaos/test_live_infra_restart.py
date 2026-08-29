"""Real container restarts (docker-gated; opt-in).

These scenarios actually terminate and restart the local docker-compose
infrastructure and prove the platform-level recovery contract:

- Redis restart     → data survives (AOF) and commands resume;
- PostgreSQL restart→ authoritative rows survive and queries resume;
- FalkorDB restart  → the graph module comes back;
- MinIO restart     → buckets and object access resume;
- PostgreSQL outage → ``/readyz`` degrades to 503 (dependency-level
  visibility) and recovers when the database returns.

They are opt-in because they mutate the shared dev stack: run them with

    make up && OT_CHAOS_LIVE=1 uv run pytest -m integration \
        tests/chaos/test_live_infra_restart.py

Without ``OT_CHAOS_LIVE=1`` (or without docker / a running stack) every test
skips. The deterministic, always-on equivalents of these scenarios live in
``test_infra_outages.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import suppress

import psycopg
import pytest
from apps.api.main import create_app
from core.config.settings import Settings, get_settings
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_COMPOSE: tuple[str, ...] = (
    "docker",
    "compose",
    "--project-name",
    "opentrading-dev",
    "-f",
    "infra/compose/docker-compose.yml",
    "--env-file",
    ".env",
)


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _postgres_up(settings: Settings) -> bool:
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=1) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def live_chaos(settings: Settings) -> Iterator[None]:
    enabled = os.environ.get("OT_CHAOS_LIVE") == "1"
    if not (enabled and _docker_available() and _postgres_up(settings)):
        pytest.skip(
            "requires OT_CHAOS_LIVE=1, the docker CLI and a running stack (`make up`)"
        )
    yield


@pytest.fixture(scope="module")
def settings() -> Settings:
    return get_settings()


def _compose(*args: str) -> None:
    subprocess.run([*_COMPOSE, *args], check=True, capture_output=True, text=True)


def _wait(predicate: Callable[[], bool], *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1.0)
    raise TimeoutError("service did not recover in time")


class TestLiveRestarts:
    def test_redis_restart_preserves_data_and_recovers(
        self, live_chaos: None, settings: Settings
    ) -> None:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=3)
        key = "opentrading:chaos:redis-restart"
        try:
            client.set(key, "survivor")
            _compose("restart", "redis")

            def ping() -> bool:
                try:
                    return bool(client.ping())
                except Exception:
                    return False

            _wait(ping)
            assert client.get(key) == b"survivor"  # AOF: nothing lost
        finally:
            client.delete(key)
            client.close()

    def test_postgres_restart_preserves_authoritative_rows(
        self, live_chaos: None, settings: Settings
    ) -> None:
        dsn = settings.postgres_dsn
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS public.chaos_recovery_probe "
                "(id text PRIMARY KEY, payload text)"
            )
            conn.execute(
                "INSERT INTO public.chaos_recovery_probe (id, payload) "
                "VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
                ("restart-row", "authoritative"),
            )
            conn.commit()

        _compose("restart", "postgres")
        _wait(lambda: _postgres_up(settings))

        with psycopg.connect(dsn) as conn:
            cursor = conn.execute(
                "SELECT payload FROM public.chaos_recovery_probe WHERE id = 'restart-row'"
            )
            row = cursor.fetchone()
            assert row is not None and row[0] == "authoritative"
            conn.execute("DROP TABLE public.chaos_recovery_probe")
            conn.commit()

    def test_falkordb_restart_roundtrip(self, live_chaos: None, settings: Settings) -> None:
        import redis

        client = redis.Redis.from_url(settings.falkordb_url, socket_connect_timeout=3)
        try:
            assert client.ping()
            _compose("restart", "falkordb")

            def ping() -> bool:
                try:
                    return bool(client.ping())
                except Exception:
                    return False

            _wait(ping)
            assert client.execute_command("GRAPH.QUERY", "opentrading_chaos", "RETURN 1")
        finally:
            with suppress(Exception):
                client.execute_command("GRAPH.DELETE", "opentrading_chaos")
            client.close()

    def test_minio_restart_roundtrip(self, live_chaos: None, settings: Settings) -> None:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        assert len(list(client.list_buckets())) >= 1
        _compose("restart", "minio")

        def buckets() -> bool:
            try:
                return len(list(client.list_buckets())) >= 1
            except Exception:
                return False

        _wait(buckets)

    def test_readyz_degrades_while_postgres_down_then_recovers(
        self, live_chaos: None, settings: Settings
    ) -> None:
        try:
            _compose("stop", "postgres")
            response = TestClient(create_app(settings=settings)).get("/readyz")
            assert response.status_code == 503
            body = response.json()
            assert body["status"] == "degraded"
            checks = {check["name"]: check for check in body["checks"]}
            assert checks["postgres"]["status"] == "unavailable"
        finally:
            _compose("start", "postgres")
            _wait(lambda: _postgres_up(settings))

        assert TestClient(create_app(settings=settings)).get("/readyz").status_code == 200
