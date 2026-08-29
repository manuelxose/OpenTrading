"""GET /readyz — aggregated dependency readiness (fake checks, no infra)."""

from __future__ import annotations

from collections.abc import Sequence

from apps.api.health import CheckFunc
from apps.api.main import create_app
from core.clock.clocks import VirtualClock
from core.config.settings import Settings
from fastapi.testclient import TestClient

from factories import FIXED_START


async def _ok(settings: Settings) -> None:
    return None


async def _down(settings: Settings) -> None:
    raise RuntimeError("dependency down")


def _client(checks: Sequence[tuple[str, CheckFunc]]) -> TestClient:
    app = create_app(
        settings=Settings(operating_mode="PAPER"),  # type: ignore[arg-type]
        clock=VirtualClock(FIXED_START),
        readiness_checks=checks,
    )
    return TestClient(app)


def test_readyz_all_dependencies_ok() -> None:
    client = _client([("postgres", _ok), ("redis", _ok)])
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["operating_mode"] == "PAPER"
    assert [check["name"] for check in body["checks"]] == ["postgres", "redis"]
    assert all(check["status"] == "ok" for check in body["checks"])
    assert all(check["detail"] is None for check in body["checks"])
    assert all(check["latency_ms"] >= 0 for check in body["checks"])


def test_readyz_degraded_when_dependency_unavailable() -> None:
    client = _client([("postgres", _ok), ("redis", _down), ("minio", _down)])
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    by_name = {check["name"]: check for check in body["checks"]}
    assert by_name["postgres"]["status"] == "ok"
    assert by_name["redis"]["status"] == "unavailable"
    assert by_name["redis"]["detail"] == "RuntimeError"
    assert by_name["minio"]["status"] == "unavailable"
