"""Integration smoke tests against the local docker-compose stack.

Run ``make up`` first. Without a reachable stack these tests skip; set
``OT_INTEGRATION=1`` (``make test-integration`` does this) to turn an
unreachable stack into a failure — that is the DoD gate.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from apps.api.main import create_app
from core.config.settings import Settings, get_settings
from fastapi.testclient import TestClient

EXPECTED_MINIO_BUCKETS = {
    "raw",
    "bronze",
    "silver",
    "gold",
    "mlflow-artifacts",
    "langfuse",
    "posttrade-artifacts",
}


def _infra_up(settings: Settings) -> bool:
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=1) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="module", autouse=True)
def require_infra(settings: Settings) -> Iterator[None]:
    if not _infra_up(settings):
        if os.environ.get("OT_INTEGRATION") == "1":
            pytest.fail("local infrastructure is unreachable — run `make up` first")
        pytest.skip("local infrastructure unreachable — run `make up` to enable")
    yield


@pytest.mark.integration
def test_postgres_extension_migrations_and_platform_tables(settings: Settings) -> None:
    with psycopg.connect(settings.postgres_dsn) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
        assert cursor.fetchone() is not None, "timescaledb extension missing"

        cursor.execute(
            "SELECT to_regclass('public.system_events'), "
            "to_regclass('public.audit_events'), "
            "to_regclass('public.alembic_version')"
        )
        assert cursor.fetchone() == (
            "system_events",
            "audit_events",
            "alembic_version",
        ), "platform tables or alembic_version missing — run `make migrate`"


@pytest.mark.integration
def test_redis_roundtrip(settings: Settings) -> None:
    import redis

    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=3)
    key = "opentrading:smoke:integration"
    try:
        assert client.set(key, "ok")
        assert client.get(key) == b"ok"
    finally:
        client.delete(key)
        client.close()


@pytest.mark.integration
def test_minio_expected_buckets_exist(settings: Settings) -> None:
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket_names = {bucket.name for bucket in client.list_buckets()}
    assert bucket_names >= EXPECTED_MINIO_BUCKETS, (
        f"missing buckets: {EXPECTED_MINIO_BUCKETS - bucket_names} — run `make init-buckets`"
    )


@pytest.mark.integration
def test_falkordb_responds_and_graph_module_loaded(settings: Settings) -> None:
    import redis

    client = redis.Redis.from_url(settings.falkordb_url, socket_connect_timeout=3)
    try:
        assert client.ping(), "falkordb did not answer PING"
        result = client.execute_command("GRAPH.QUERY", "opentrading_smoke", "RETURN 1")
        assert result is not None, "graph module did not answer GRAPH.QUERY"
    finally:
        client.execute_command("GRAPH.DELETE", "opentrading_smoke")
        client.close()


@pytest.mark.integration
def test_readyz_end_to_end_all_dependencies_ok(settings: Settings) -> None:
    response = TestClient(create_app(settings=settings)).get("/readyz")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    checks = {check["name"]: check for check in body["checks"]}
    assert set(checks) == {"postgres", "redis", "minio", "falkordb"}
    assert all(check["status"] == "ok" for check in checks.values())
