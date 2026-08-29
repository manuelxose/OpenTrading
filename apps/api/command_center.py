"""Read-only Command Center API backed by canonical platform persistence.

This module projects persisted decisions for operators.  It deliberately contains no
trading, sizing, fusion, or risk-decision logic (INV-1/INV-4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from adapters.market_data.catalog_db import dataset_versions_table
from core.config.settings import Settings, ensure_psycopg_dsn
from engines.execution.persistence import (
    execution_orders_table,
    execution_positions_table,
    reconciliation_runs_table,
    safe_mode_state_table,
)
from engines.posttrade.persistence import posttrade_reviews_table
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Engine, String, cast, create_engine, desc, select

from apps.worker.cli import build_default_config
from apps.worker.persistence import (
    paper_accounts_table,
    pipeline_runs_table,
    trade_contexts_table,
    trade_lifecycles_table,
)

SCHEMA_VERSION = "1.0.0"
COLLECTIONS = (
    "research",
    "signals",
    "orders",
    "trades",
    "positions",
    "backtests",
    "memory",
    "agents",
)


class CommandCenterDataSource(Protocol):
    def overview(self, now: datetime) -> dict[str, Any]: ...
    def collection(self, resource: str, limit: int) -> dict[str, Any]: ...
    def risk(self) -> dict[str, Any]: ...
    def trade_detail(self, trade_id: str) -> dict[str, Any] | None: ...


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "hex"):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _row(row: Any) -> dict[str, Any]:
    result = _json(dict(row._mapping))
    if not isinstance(result, dict):  # defensive: row mappings always project to objects
        raise TypeError("database row did not serialize to an object")
    return result


class PostgresCommandCenterDataSource:
    """Operational projections from PostgreSQL, the transactional source of truth."""

    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self.settings = settings
        self.engine = engine or create_engine(
            ensure_psycopg_dsn(settings.postgres_dsn), pool_pre_ping=True
        )

    def overview(self, now: datetime) -> dict[str, Any]:
        with self.engine.connect() as conn:
            account_row = conn.execute(
                select(paper_accounts_table)
                .order_by(desc(paper_accounts_table.c.updated_at))
                .limit(1)
            ).first()
            reconciliation = conn.execute(
                select(reconciliation_runs_table)
                .order_by(desc(reconciliation_runs_table.c.compared_at))
                .limit(1)
            ).first()
            safe_mode = conn.execute(select(safe_mode_state_table).limit(1)).first()
            contexts = conn.execute(
                select(trade_contexts_table)
                .order_by(desc(trade_contexts_table.c.updated_at))
                .limit(100)
            ).all()
            latest_dataset = conn.execute(
                select(dataset_versions_table.c.available_time_max)
                .where(dataset_versions_table.c.state == "SEALED")
                .order_by(desc(dataset_versions_table.c.available_time_max))
                .limit(1)
            ).first()

        account = _row(account_row) if account_row else None
        portfolio_snapshot = self._latest_fragment(contexts, "portfolio_snapshot")
        gross = portfolio_snapshot.get("gross_exposure") if portfolio_snapshot else None
        net = portfolio_snapshot.get("net_exposure") if portfolio_snapshot else None
        latest_at = latest_dataset.available_time_max if latest_dataset else None
        freshness_seconds = (now - latest_at).total_seconds() if latest_at else None
        freshness = (
            "UNKNOWN"
            if freshness_seconds is None
            else "FRESH"
            if freshness_seconds <= self.settings.market_data_stale_after_seconds
            else "STALE"
        )
        safe_active = bool(safe_mode and safe_mode.active)
        mt4_status = (
            "UNKNOWN"
            if reconciliation is None
            else "CONNECTED"
            if reconciliation.broker_reachable and reconciliation.broker_connected
            else "DISCONNECTED"
        )
        equity = Decimal(str(account["equity"])) if account else None
        peak = Decimal(str(account["peak_equity"])) if account else None
        drawdown = (
            float(Decimal(str(portfolio_snapshot["drawdown"])) * 100)
            if portfolio_snapshot and portfolio_snapshot.get("drawdown") is not None
            else float(max(Decimal("0"), peak - equity) / peak * 100)
            if equity is not None and peak
            else None
        )
        return {
            "asOf": now.isoformat(),
            "account": {
                "nav": str(equity) if equity is not None else None,
                "equity": str(equity) if equity is not None else None,
                "currency": account["currency"] if account else None,
            },
            "performance": {
                "pnl": account["daily_pnl"] if account else None,
                "realizedPnl": account["realized_pnl"] if account else None,
                "drawdownPct": drawdown,
            },
            "exposure": {
                "gross": str(gross) if gross is not None else None,
                "net": str(net) if net is not None else None,
                "asOf": portfolio_snapshot.get("as_of") if portfolio_snapshot else None,
                "status": "CURRENT_MARK" if portfolio_snapshot else "UNAVAILABLE",
            },
            "riskStatus": "SAFE_MODE" if safe_active else "NORMAL",
            "mt4Status": mt4_status,
            "dataFreshness": {
                "status": freshness,
                "latestAt": latest_at.isoformat() if latest_at else None,
                "ageSeconds": int(freshness_seconds) if freshness_seconds is not None else None,
            },
        }

    def collection(self, resource: str, limit: int) -> dict[str, Any]:
        table = {
            "research": pipeline_runs_table,
            "signals": trade_contexts_table,
            "orders": execution_orders_table,
            "trades": posttrade_reviews_table,
            "positions": execution_positions_table,
        }.get(resource)
        if table is None:
            return {
                "resource": resource,
                "items": [],
                "total": 0,
                "limit": limit,
                "availability": "NOT_IMPLEMENTED_BY_PLATFORM",
            }
        order_column = next(
            (
                table.c[name]
                for name in ("updated_at", "created_at", "started_at")
                if name in table.c
            ),
            None,
        )
        query = select(table)
        if resource == "research":
            query = query.where(pipeline_runs_table.c.stage == "RESEARCH")
        if resource == "positions":
            query = query.where(execution_positions_table.c.closed_at.is_(None))
        if order_column is not None:
            query = query.order_by(desc(order_column))
        with self.engine.connect() as conn:
            rows = conn.execute(query.limit(limit)).all()
        items = [_row(item) for item in rows]
        if resource == "signals":
            items = [
                {
                    "trace_id": item["trace_id"],
                    "instrument_id": item["instrument_id"],
                    "updated_at": item["updated_at"],
                    **item["fragments"],
                }
                for item in items
            ]
        return {"resource": resource, "items": items, "total": len(items), "limit": limit}

    def risk(self) -> dict[str, Any]:
        with self.engine.connect() as conn:
            safe = conn.execute(select(safe_mode_state_table).limit(1)).first()
            positions = conn.execute(
                select(execution_positions_table).where(
                    execution_positions_table.c.closed_at.is_(None)
                )
            ).all()
            orders = conn.execute(
                select(execution_orders_table).where(
                    execution_orders_table.c.state.in_(
                        ("SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED")
                    )
                )
            ).all()
            contexts = conn.execute(
                select(trade_contexts_table)
                .order_by(desc(trade_contexts_table.c.updated_at))
                .limit(100)
            ).all()
        decisions = [_row(row)["fragments"].get("risk_decision") for row in contexts]
        decisions = [decision for decision in decisions if decision]
        rejected = [
            decision
            for decision in decisions
            if str(decision.get("decision", decision.get("action", ""))).upper() == "REJECT"
        ][:20]
        policy = build_default_config(self.settings).risk
        portfolio_snapshot = self._latest_fragment(contexts, "portfolio_snapshot")
        gross_exposure = (
            Decimal(str(portfolio_snapshot["gross_exposure"]))
            if portfolio_snapshot and portfolio_snapshot.get("gross_exposure") is not None
            else None
        )
        equity = (
            Decimal(str(portfolio_snapshot["equity"]))
            if portfolio_snapshot and portfolio_snapshot.get("equity") is not None
            else None
        )
        daily_loss = (
            Decimal(str(portfolio_snapshot["daily_loss"]))
            if portfolio_snapshot and portfolio_snapshot.get("daily_loss") is not None
            else None
        )
        drawdown = (
            max(Decimal("0"), Decimal(str(portfolio_snapshot["drawdown"])))
            if portfolio_snapshot and portfolio_snapshot.get("drawdown") is not None
            else None
        )
        utilization = [
            self._utilization("totalExposure", gross_exposure, policy.max_total_exposure),
            self._utilization("dailyLoss", daily_loss, policy.max_daily_loss, inclusive=True),
            self._utilization("drawdown", drawdown, policy.max_drawdown_pct, inclusive=True),
            self._utilization(
                "openPositions", Decimal(len(positions)), Decimal(policy.max_positions)
            ),
            self._utilization(
                "pendingOrders", Decimal(len(orders)), Decimal(policy.max_pending_orders)
            ),
            self._utilization(
                "leverage",
                gross_exposure / equity if gross_exposure is not None and equity else None,
                policy.max_leverage,
            ),
        ]
        return {
            "configuredLimits": [
                {"key": key, "value": _json(value), "source": "active deterministic policy"}
                for key, value in {
                    "maxRiskPerTrade": policy.max_risk_per_trade,
                    "maxTotalExposure": policy.max_total_exposure,
                    "maxInstrumentExposure": policy.max_instrument_exposure,
                    "maxCurrencyExposure": policy.max_currency_exposure,
                    "maxLeverage": policy.max_leverage,
                    "maxPositions": policy.max_positions,
                    "maxPendingOrders": policy.max_pending_orders,
                    "maxDailyLoss": policy.max_daily_loss,
                    "maxDrawdownPct": policy.max_drawdown_pct,
                    "maxConsecutiveLosses": policy.max_consecutive_losses,
                    "marketDataMaxAgeSeconds": policy.market_data_max_age_seconds,
                    "heartbeatMaxAgeSeconds": policy.heartbeat_max_age_seconds,
                }.items()
            ],
            "currentUtilization": utilization,
            "breaches": [item for item in utilization if item["isBreached"]],
            "utilizationAsOf": portfolio_snapshot.get("as_of") if portfolio_snapshot else None,
            "recentRejections": rejected,
            "killSwitch": {
                "status": "NOT_PERSISTED",
                "scopes": ["strategy", "instrument", "portfolio", "emergency", "deadMan"],
                "note": "Scoped kill-switch state is not yet persisted by this platform phase.",
            },
            "safeMode": {
                "active": bool(safe and safe.active),
                "reasonCodes": list(safe.reason_codes) if safe else [],
                "since": safe.since.isoformat() if safe and safe.since else None,
                "note": safe.note if safe else None,
            },
        }

    @staticmethod
    def _utilization(
        key: str, current: Decimal | None, limit: Decimal, *, inclusive: bool = False
    ) -> dict[str, Any]:
        return {
            "key": key,
            "current": str(current) if current is not None else None,
            "limit": str(limit),
            "utilizationPct": (
                float(current / limit * 100) if current is not None and limit else None
            ),
            "isBreached": (current >= limit if inclusive else current > limit)
            if current is not None
            else None,
            "status": "AVAILABLE" if current is not None else "UNAVAILABLE",
        }

    @staticmethod
    def _latest_fragment(rows: Any, key: str) -> dict[str, Any] | None:
        for row in rows:
            fragments = _row(row).get("fragments", {})
            value = fragments.get(key) if isinstance(fragments, dict) else None
            if isinstance(value, dict):
                return value
        return None

    def trade_detail(self, trade_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            review = conn.execute(
                select(posttrade_reviews_table).where(
                    cast(posttrade_reviews_table.c.trade_id, String) == trade_id
                )
            ).first()
            lifecycle = conn.execute(
                select(trade_lifecycles_table).where(
                    cast(trade_lifecycles_table.c.trade_id, String) == trade_id
                )
            ).first()
            if review is None and lifecycle is None:
                return None
            if review is not None:
                trace_id = review.trace_id
            else:
                assert lifecycle is not None  # both absent returned above
                trace_id = lifecycle.trace_id
            context = conn.execute(
                select(trade_contexts_table).where(trade_contexts_table.c.trace_id == trace_id)
            ).first()
            order = None
            if lifecycle is not None and lifecycle.order_intent_id:
                order = conn.execute(
                    select(execution_orders_table).where(
                        execution_orders_table.c.order_intent_id == lifecycle.order_intent_id
                    )
                ).first()
        fragments = _row(context)["fragments"] if context else {}
        lifecycle_data = _row(lifecycle) if lifecycle else None
        order_data = _row(order) if order else None
        review_data = _row(review) if review else None
        stages = [
            ("sourceData", fragments.get("source_data") or fragments.get("snapshot")),
            ("tradingAgentsAnalysis", fragments.get("llm")),
            ("quantSignal", fragments.get("quant")),
            ("fusedSignal", fragments.get("fused")),
            ("riskDecision", fragments.get("risk_decision")),
            ("orderIntent", fragments.get("order_intent")),
            ("brokerExecution", order_data),
            ("positionLifecycle", lifecycle_data),
            ("postmortem", review_data),
        ]
        return {
            "tradeId": trade_id,
            "traceId": str(trace_id),
            "stages": [
                {
                    "key": key,
                    "status": "AVAILABLE" if payload else "NOT_RECORDED",
                    "payload": payload,
                }
                for key, payload in stages
            ],
        }


def build_command_center_router(
    source: CommandCenterDataSource,
    settings: Settings,
    system_health: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/command-center", tags=["command-center"])

    def envelope(data: Any) -> dict[str, Any]:
        return {"schemaVersion": SCHEMA_VERSION, "data": data}

    @router.get("/overview")
    def overview() -> dict[str, Any]:
        data = source.overview(datetime.now(UTC))
        data["operatingMode"] = settings.operating_mode.value
        return envelope(data)

    def collection_handler(resource: str) -> Any:
        def handler(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
            return envelope(source.collection(resource, limit))

        return handler

    for resource in COLLECTIONS:
        router.add_api_route(
            f"/{resource}",
            collection_handler(resource),
            methods=["GET"],
            name=f"list-{resource}",
        )

    @router.get("/risk")
    def risk() -> dict[str, Any]:
        return envelope(source.risk())

    @router.get("/trades/{trade_id}")
    def trade_detail(trade_id: str) -> dict[str, Any]:
        detail = source.trade_detail(trade_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Trade not found")
        return envelope(detail)

    @router.get("/system")
    async def system() -> dict[str, Any]:
        checks = await system_health()
        return envelope(
            {
                "status": (
                    "HEALTHY" if all(check["status"] == "ok" for check in checks) else "DEGRADED"
                ),
                "operatingMode": settings.operating_mode.value,
                "dependencies": checks,
            }
        )

    return router
