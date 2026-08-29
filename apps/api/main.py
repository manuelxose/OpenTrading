"""OpenTrading API service (core runtime, Python 3.12).

Operational endpoints:

- ``GET /healthz`` — liveness + operating mode + clock time.
- ``GET /readyz`` — readiness: probes PostgreSQL, Redis, MinIO and FalkorDB
  (§31 observability); returns 200 when every dependency is reachable, 503
  otherwise.
- ``GET /api/v1/contracts`` — catalog of the canonical domain contracts.
- ``GET /api/v1/market-data/*`` — point-in-time bars and snapshots (Phase 1).

Trading endpoints arrive with Phases 5+ (risk), 7 (paper) and 8 (LIVE_GATED).
"""

import secrets
from collections.abc import Sequence
from datetime import timedelta

from adapters.market_data.catalog import Catalog
from adapters.market_data.repository import MarketDataRepository
from core.audit.audit import AuditLogger
from core.audit.persistence import PostgresAuditSink
from core.clock.clocks import Clock, SystemClock
from core.config.settings import Settings, get_settings
from core.domain.enums import OperatingMode
from core.observability.metrics import OperationalMetrics, metrics
from core.schemas import CANONICAL_CONTRACTS
from core.security import install_redacting_logging
from engines.execution.emergency import EmergencyController, EmergencyPolicy
from engines.execution.emergency_persistence import PostgresEmergencyStore
from engines.execution.live_gate import HumanApprovalGate, LiveGateConfig
from engines.execution.live_gate_persistence import PostgresApprovalStore
from engines.live_auto.config import LiveAutoConfig
from engines.live_auto.persistence import PostgresLiveAutoStore
from engines.live_auto.registry import LiveAutoRegistry
from fastapi import FastAPI, Header, HTTPException, Response, status
from prometheus_client import make_asgi_app

from apps.api.command_center import (
    CommandCenterDataSource,
    PostgresCommandCenterDataSource,
    build_command_center_router,
)
from apps.api.emergency import build_emergency_router
from apps.api.health import (
    DEFAULT_READINESS_CHECKS,
    CheckFunc,
    result_dicts,
    run_readiness_checks,
)
from apps.api.live_auto import build_live_auto_router
from apps.api.live_gated import OperatorResolver, build_live_gated_router
from apps.api.market_data import build_default_repository, build_market_data_router


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    readiness_checks: Sequence[tuple[str, CheckFunc]] | None = None,
    market_data_repository: MarketDataRepository | None = None,
    market_data_catalog: Catalog | None = None,
    operational_metrics: OperationalMetrics | None = None,
    command_center_data_source: CommandCenterDataSource | None = None,
    live_gate: HumanApprovalGate | None = None,
    authenticate_operator: OperatorResolver | None = None,
    emergency: EmergencyController | None = None,
    live_auto_registry: LiveAutoRegistry | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app_clock = clock or SystemClock()
    app_metrics = operational_metrics or metrics
    app_readiness_checks = (
        readiness_checks if readiness_checks is not None else DEFAULT_READINESS_CHECKS
    )
    operating_mode = app_settings.operating_mode

    app = FastAPI(
        title="OpenTrading API",
        version=app_settings.schema_version,
        description="Autonomous Quantitative Trading & Research Platform — core runtime.",
    )

    # Live modes mount the operator-governed mutation surfaces (LIVE_GATED
    # approvals + LIVE_AUTO governance + emergency controls). LIVE_AUTO does
    # not need the human approval signing key, but the operator token and the
    # deterministic registry are mandatory. The operating mode itself comes
    # from OT_OPERATING_MODE at process start and can never be changed by an
    # LLM, RD-Agent, strategy code or any API call (INV-1, INV-8).
    if operating_mode in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO) and (
        live_gate is None or authenticate_operator is None or live_auto_registry is None
    ):
        operator_secret = app_settings.live_operator_token
        if operating_mode is OperatingMode.LIVE_GATED:
            signing_secret = app_settings.live_approval_signing_key
            if signing_secret is None or operator_secret is None:
                raise RuntimeError(
                    "LIVE_GATED requires OT_LIVE_APPROVAL_SIGNING_KEY and OT_LIVE_OPERATOR_TOKEN"
                )
        elif operator_secret is None:
            raise RuntimeError("LIVE_AUTO requires OT_LIVE_OPERATOR_TOKEN")

        def configured_operator(
            authorization: str = Header(default=""),
        ) -> str:
            expected = f"Bearer {operator_secret.get_secret_value()}"
            if not secrets.compare_digest(authorization, expected):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
            return f"{operating_mode.value.lower()}-operator"

        authenticate_operator = configured_operator

        if emergency is None:
            emergency = EmergencyController(
                PostgresEmergencyStore(app_settings.postgres_dsn),
                app_clock,
                policy=EmergencyPolicy(
                    dead_man_switch_enabled=app_settings.emergency_dead_man_enabled,
                    heartbeat_timeout=timedelta(
                        seconds=app_settings.emergency_heartbeat_timeout_seconds
                    ),
                    cancel_pending_on_emergency_kill=app_settings.emergency_cancel_pending_on_kill,
                    flatten_on_emergency_kill=app_settings.emergency_flatten_on_kill,
                    flatten_on_heartbeat_loss=app_settings.emergency_flatten_on_heartbeat_loss,
                ),
            )

        if operating_mode is OperatingMode.LIVE_GATED and live_gate is None:
            signing_secret = app_settings.live_approval_signing_key
            if signing_secret is None:
                raise RuntimeError(
                    "LIVE_GATED requires OT_LIVE_APPROVAL_SIGNING_KEY and OT_LIVE_OPERATOR_TOKEN"
                )
            live_gate = HumanApprovalGate(
                store=PostgresApprovalStore(app_settings.postgres_dsn),
                clock=app_clock,
                signing_key=signing_secret.get_secret_value().encode(),
                config=LiveGateConfig(
                    approval_ttl=timedelta(seconds=app_settings.live_approval_ttl_seconds),
                    max_price_drift_bps=app_settings.live_max_price_drift_bps,
                    max_quote_age=timedelta(seconds=app_settings.live_max_quote_age_seconds),
                    broker_demo=app_settings.live_broker_demo,
                    max_live_quantity=app_settings.live_max_quantity,
                ),
            )

        if live_auto_registry is None:
            live_auto_registry = LiveAutoRegistry(
                PostgresLiveAutoStore(app_settings.postgres_dsn),
                LiveAutoConfig.from_settings(app_settings),
                app_clock,
                audit=AuditLogger(PostgresAuditSink(app_settings.postgres_dsn), app_clock),
            )

    # Phase 1 market data: defaults are built from settings (MinIO + PostgreSQL);
    # tests inject in-memory doubles. Construction performs no network I/O.
    if market_data_repository is not None and market_data_catalog is None:
        raise ValueError("market_data_catalog must be provided with market_data_repository")
    if market_data_repository is None:
        repository, catalog = build_default_repository(app_settings)
    else:
        assert market_data_catalog is not None  # checked above
        repository = market_data_repository
        catalog = market_data_catalog
    app.include_router(build_market_data_router(repository, catalog, app_clock, app_metrics))
    command_source = command_center_data_source or PostgresCommandCenterDataSource(app_settings)

    async def command_system_health() -> list[dict[str, object]]:
        return result_dicts(await run_readiness_checks(app_settings, app_readiness_checks))

    app.include_router(
        build_command_center_router(command_source, app_settings, command_system_health)
    )
    if operating_mode is OperatingMode.LIVE_GATED and (live_gate is None) != (
        authenticate_operator is None
    ):
        raise ValueError("live_gate and authenticate_operator must be configured together")
    if live_gate is not None and authenticate_operator is not None:
        app.include_router(build_live_gated_router(live_gate, authenticate_operator))
    if live_auto_registry is not None and authenticate_operator is not None:
        app.include_router(build_live_auto_router(live_auto_registry, authenticate_operator))
    if emergency is not None and authenticate_operator is not None:
        app.include_router(build_emergency_router(emergency, authenticate_operator))
    app.mount("/metrics", make_asgi_app(registry=app_metrics.registry))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        app_metrics.set_service_health(app_settings.app_name, True)
        return {
            "status": "ok",
            "service": app_settings.app_name,
            "operating_mode": app_settings.operating_mode.value,
            "schema_version": app_settings.schema_version,
            "now": app_clock.now().isoformat(),
        }

    @app.get("/readyz")
    async def readyz(response: Response) -> dict[str, object]:
        results = await run_readiness_checks(app_settings, app_readiness_checks)
        for result in results:
            app_metrics.observe_dependency(
                result.name, result.latency_ms / 1000, result.status == "ok"
            )
        ready = all(result.status == "ok" for result in results)
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if ready else "degraded",
            "service": app_settings.app_name,
            "operating_mode": app_settings.operating_mode.value,
            "checks": result_dicts(results),
        }

    @app.get("/api/v1/contracts")
    def contracts() -> dict[str, object]:
        return {
            "schema_version": app_settings.schema_version,
            "contracts": [
                {"name": name, "schema_version": contract.SCHEMA_VERSION}
                for name, contract in CANONICAL_CONTRACTS.items()
            ],
        }

    return app


#: ASGI entrypoint for uvicorn: ``uvicorn apps.api.main:app``.
# Redacting logging is installed at import so secrets loaded in LIVE_GATED
# mode (signing key, operator token) can never reach logs (§29 / ADR-0025).
install_redacting_logging()
app = create_app()
