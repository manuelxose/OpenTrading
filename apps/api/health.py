"""Dependency readiness checks backing ``GET /readyz`` (§31 observability).

Each check is isolated and time-bounded; a failing dependency degrades to a
structured ``unavailable`` result instead of raising. Checks never log
credentials — error details carry only the exception class name.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass

from core.config.settings import Settings

__all__ = [
    "DEFAULT_READINESS_CHECKS",
    "CheckFunc",
    "HealthCheckResult",
    "check_falkordb",
    "check_minio",
    "check_postgres",
    "check_redis",
    "run_check",
    "run_readiness_checks",
]

#: A check probes one dependency and raises on failure.
CheckFunc = Callable[[Settings], Awaitable[None]]


@dataclass(frozen=True)
class HealthCheckResult:
    """Outcome of one dependency probe."""

    name: str
    status: str  # "ok" | "unavailable"
    latency_ms: int
    detail: str | None = None


async def check_postgres(settings: Settings) -> None:
    """Connect to PostgreSQL and run ``SELECT 1``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(
        settings.postgres_dsn, connect_timeout=int(settings.readiness_timeout_seconds)
    ) as conn:
        cursor = await conn.execute("SELECT 1")
        await cursor.fetchone()


async def check_redis(settings: Settings) -> None:
    """PING Redis (cache / locks / streams)."""
    import redis.asyncio as redis_asyncio

    client = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_falkordb(settings: Settings) -> None:
    """PING FalkorDB (speaks RESP, so the Redis client works)."""
    import redis.asyncio as redis_asyncio

    client = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        settings.falkordb_url,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_minio(settings: Settings) -> None:
    """Verify MinIO is reachable and the readiness bucket exists."""
    from minio import Minio

    def _probe() -> None:
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not client.bucket_exists(settings.minio_readiness_bucket):
            raise RuntimeError(f"bucket {settings.minio_readiness_bucket!r} missing")

    await asyncio.to_thread(_probe)


#: Checks exercised by ``GET /readyz``.
DEFAULT_READINESS_CHECKS: Sequence[tuple[str, CheckFunc]] = (
    ("postgres", check_postgres),
    ("redis", check_redis),
    ("minio", check_minio),
    ("falkordb", check_falkordb),
)


async def run_check(name: str, settings: Settings, func: CheckFunc) -> HealthCheckResult:
    """Run one probe with a hard timeout; never raise."""
    start = time.perf_counter()
    status: str
    detail: str | None
    try:
        await asyncio.wait_for(func(settings), timeout=settings.readiness_timeout_seconds)
    except TimeoutError:
        status, detail = "unavailable", "timeout"
    except Exception as exc:
        status, detail = "unavailable", type(exc).__name__
    else:
        status, detail = "ok", None
    return HealthCheckResult(
        name=name,
        status=status,
        latency_ms=int((time.perf_counter() - start) * 1000),
        detail=detail,
    )


async def run_readiness_checks(
    settings: Settings, checks: Sequence[tuple[str, CheckFunc]]
) -> list[HealthCheckResult]:
    """Probe every dependency concurrently and return one result per check."""
    return list(await asyncio.gather(*(run_check(name, settings, func) for name, func in checks)))


def result_dicts(results: Sequence[HealthCheckResult]) -> list[dict[str, object]]:
    """Serializable projection for API responses."""
    return [asdict(result) for result in results]
