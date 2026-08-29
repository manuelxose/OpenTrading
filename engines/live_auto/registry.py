"""LIVE_AUTO governance registry (Phase 11).

The registry is the single deterministic authority over automated execution:

- promotion ``LIVE_GATED → LIVE_AUTO`` happens only through
  :meth:`LiveAutoRegistry.promote`, which is reachable exclusively from the
  operator-authenticated API and writes an immutable audit event;
- every automated order must pass
  :meth:`LiveAutoRegistry.assert_submission_authorized`, which re-checks the
  capability flag, the strategy's LIVE_AUTO lifecycle state, the Risk Engine
  decision, per-strategy risk budgets, platform ceilings, quote freshness and
  the global realized-loss limit — no LLM, no strategy process, no RD-Agent
  can call or satisfy this check by itself.

The registry reads durable state on every submission (like the human approval
gate reads the approval store), so demotions and loss-limit breaches take
effect immediately, without restarts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from core.audit.audit import AuditLogger
from core.clock.clocks import Clock
from core.domain.enums import OperatingMode, RiskDecisionType, StrategyState
from core.schemas.trading import OrderIntent, RiskDecision

from engines.execution.live_gate import PriceContext
from engines.live_auto.config import LiveAutoConfig, LiveAutoViolation

__all__ = [
    "InMemoryLiveAutoStore",
    "LiveAutoRegistry",
    "LiveAutoStore",
    "LiveAutoStrategyRecord",
]


@dataclass(frozen=True, slots=True)
class LiveAutoStrategyRecord:
    """Durable row of the LIVE_AUTO registry for one strategy."""

    strategy_id: str
    strategy_version: str
    from_state: StrategyState
    state: StrategyState
    risk_budget: Decimal
    capital_allocation: Decimal
    promoted_by: str
    promoted_at: datetime
    evidence: tuple[str, ...]
    active: bool
    demoted_by: str | None = None
    demoted_at: datetime | None = None
    demote_reason: str | None = None


class LiveAutoStore(Protocol):
    """Durable storage for the registry and the realized-PnL ledger."""

    def get_strategy(self, strategy_id: str) -> LiveAutoStrategyRecord | None: ...

    def save_strategy(self, record: LiveAutoStrategyRecord) -> None: ...

    def list_strategies(self) -> tuple[LiveAutoStrategyRecord, ...]: ...

    def append_pnl(
        self,
        *,
        ledger_id: UUID,
        strategy_id: str,
        amount: Decimal,
        recorded_by: str,
        recorded_at: datetime,
        source: str,
    ) -> None: ...

    def total_pnl(self) -> Decimal: ...


class InMemoryLiveAutoStore:
    """Append-oriented in-memory store for tests and short-lived processes."""

    def __init__(self) -> None:
        self._strategies: dict[str, LiveAutoStrategyRecord] = {}
        self._pnl: list[tuple[UUID, str, Decimal, str, datetime, str]] = []

    def get_strategy(self, strategy_id: str) -> LiveAutoStrategyRecord | None:
        return self._strategies.get(strategy_id)

    def save_strategy(self, record: LiveAutoStrategyRecord) -> None:
        self._strategies[record.strategy_id] = record

    def list_strategies(self) -> tuple[LiveAutoStrategyRecord, ...]:
        return tuple(self._strategies.values())

    def append_pnl(
        self,
        *,
        ledger_id: UUID,
        strategy_id: str,
        amount: Decimal,
        recorded_by: str,
        recorded_at: datetime,
        source: str,
    ) -> None:
        self._pnl.append((ledger_id, strategy_id, amount, recorded_by, recorded_at, source))

    def total_pnl(self) -> Decimal:
        return sum((row[2] for row in self._pnl), start=Decimal("0"))


def _audit_metadata(**values: object) -> dict[str, Any]:
    """Normalize values into JSON-serializable audit metadata."""
    metadata: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, Decimal):
            metadata[key] = str(value)
        elif isinstance(value, datetime):
            metadata[key] = value.isoformat()
        elif isinstance(value, UUID):
            metadata[key] = str(value)
        elif isinstance(value, (StrategyState, OperatingMode)):
            metadata[key] = value.value
        elif isinstance(value, (str, int, float, bool)) or value is None:
            metadata[key] = value
        else:
            metadata[key] = str(value)
    return metadata


class LiveAutoRegistry:
    """Deterministic governance authority for LIVE_AUTO execution."""

    def __init__(
        self,
        store: LiveAutoStore,
        config: LiveAutoConfig,
        clock: Clock,
        audit: AuditLogger | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._clock = clock
        self._audit = audit

    # ── Governance actions (operator API only) ────────────────────────────
    def promote(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        from_state: StrategyState,
        risk_budget: Decimal,
        capital_allocation: Decimal,
        actor: str,
        evidence: tuple[str, ...] = (),
    ) -> LiveAutoStrategyRecord:
        """Promote ``LIVE_GATED → LIVE_AUTO``. Explicit admin action only."""
        self._config.assert_enabled()
        if from_state is not StrategyState.LIVE_GATED:
            raise LiveAutoViolation(
                "LIVE_AUTO promotion is only allowed from the LIVE_GATED lifecycle state"
            )
        if not strategy_id or not strategy_version:
            raise LiveAutoViolation("promotion requires a strategy id and version")
        if risk_budget <= 0:
            raise LiveAutoViolation("per-strategy risk budget must be positive")
        ceiling = self._config.strategy_risk_budget_ceilings.get(strategy_id)
        if ceiling is not None and risk_budget > ceiling:
            raise LiveAutoViolation(
                f"risk budget {risk_budget} exceeds the configured ceiling {ceiling}"
            )
        if capital_allocation <= 0:
            raise LiveAutoViolation("capital allocation must be positive")
        existing = self._store.get_strategy(strategy_id)
        if existing is not None and existing.active:
            raise LiveAutoViolation(f"strategy {strategy_id!r} is already in LIVE_AUTO")

        active = tuple(r for r in self._store.list_strategies() if r.active)
        if len(active) >= self._config.max_strategies:
            raise LiveAutoViolation(
                f"LIVE_AUTO strategy ceiling reached ({self._config.max_strategies})"
            )
        allocated = sum((r.capital_allocation for r in active), start=Decimal("0"))
        assert self._config.max_capital is not None  # assert_enabled guarantees it
        if allocated + capital_allocation > self._config.max_capital:
            raise LiveAutoViolation(
                f"capital allocation would exceed the LIVE_AUTO ceiling "
                f"({self._config.max_capital})"
            )
        now = self._clock.now()
        record = LiveAutoStrategyRecord(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            from_state=from_state,
            state=StrategyState.LIVE_AUTO,
            risk_budget=risk_budget,
            capital_allocation=capital_allocation,
            promoted_by=actor,
            promoted_at=now,
            evidence=tuple(evidence),
            active=True,
        )
        self._store.save_strategy(record)
        if self._audit is not None:
            self._audit.record(
                "live_auto.strategy_promoted",
                actor=actor,
                target=strategy_id,
                metadata=_audit_metadata(
                    from_state=from_state,
                    to_state=record.state,
                    strategy_version=strategy_version,
                    risk_budget=risk_budget,
                    capital_allocation=capital_allocation,
                    evidence=list(evidence),
                    promoted_at=now,
                ),
            )
        return record

    def demote(
        self, *, strategy_id: str, actor: str, reason: str
    ) -> LiveAutoStrategyRecord:
        """Demote a LIVE_AUTO strategy (retire it). Explicit admin action only."""
        existing = self._store.get_strategy(strategy_id)
        if existing is None or not existing.active:
            raise LiveAutoViolation(f"strategy {strategy_id!r} is not in LIVE_AUTO")
        if not reason:
            raise LiveAutoViolation("demotion requires a reason")
        now = self._clock.now()
        record = replace(
            existing,
            active=False,
            state=StrategyState.RETIRED,
            demoted_by=actor,
            demoted_at=now,
            demote_reason=reason,
        )
        self._store.save_strategy(record)
        if self._audit is not None:
            self._audit.record(
                "live_auto.strategy_demoted",
                actor=actor,
                target=strategy_id,
                metadata=_audit_metadata(
                    from_state=StrategyState.LIVE_AUTO,
                    to_state=record.state,
                    reason=reason,
                    demoted_at=now,
                ),
            )
        return record

    def record_realized_pnl(
        self, *, strategy_id: str, amount: Decimal, actor: str, source: str
    ) -> None:
        """Append one realized-PnL entry to the global LIVE_AUTO loss ledger.

        Operator-authenticated (or deterministic posttrade integration) only.
        Entries are append-only; the authorizer reads the cumulative sum.
        """
        if self._store.get_strategy(strategy_id) is None:
            raise LiveAutoViolation(
                f"strategy {strategy_id!r} is not in the LIVE_AUTO registry"
            )
        if amount == 0:
            raise LiveAutoViolation("realized-PnL entries must be non-zero")
        if not source:
            raise LiveAutoViolation("realized-PnL entries require a source")
        now = self._clock.now()
        ledger_id = uuid4()
        self._store.append_pnl(
            ledger_id=ledger_id,
            strategy_id=strategy_id,
            amount=amount,
            recorded_by=actor,
            recorded_at=now,
            source=source,
        )
        if self._audit is not None:
            self._audit.record(
                "live_auto.pnl_recorded",
                actor=actor,
                target=strategy_id,
                metadata=_audit_metadata(
                    ledger_id=ledger_id,
                    amount=amount,
                    source=source,
                    recorded_at=now,
                ),
            )

    # ── Automated-order authorization (deterministic, called per submission) ─
    def assert_submission_authorized(
        self,
        *,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        price_context: PriceContext,
    ) -> None:
        """Deterministic gate for every LIVE_AUTO order.

        Succeeds only when the capability is enabled, the strategy holds the
        LIVE_AUTO lifecycle state in the registry, the Risk Engine decision
        matches the intent exactly, the per-strategy budget and every platform
        ceiling hold, and the global loss limit has not been breached. Every
        outcome (authorized or denied) is audited.
        """
        try:
            record = self._assert_submission_impl(
                intent=intent, risk_decision=risk_decision, price_context=price_context
            )
        except LiveAutoViolation as exc:
            self._audit_denied(intent, str(exc))
            raise
        if self._audit is not None:
            self._audit.record(
                "live_auto.order_authorized",
                actor="live-auto-registry",
                target=intent.strategy_id,
                metadata=_audit_metadata(
                    order_intent_id=intent.order_intent_id,
                    risk_decision_id=intent.risk_decision_id,
                    instrument_id=intent.instrument_id,
                    quantity=intent.quantity,
                    risk_amount=risk_decision.risk_amount,
                    risk_budget=record.risk_budget,
                ),
            )

    def assert_wire_authorized(self, *, intent: OrderIntent) -> None:
        """Wire-boundary re-check inside the MT4 client (defense in depth).

        Re-verifies every deterministic invariant derivable from the intent
        alone at the moment the command reaches the execution client: enabled
        capability, LIVE_AUTO lifecycle state, platform ceilings, quantity
        ceiling and the global loss limit. The Risk Engine decision was already
        consumed by :meth:`assert_submission_authorized` before persistence.
        """
        try:
            self._assert_wire_impl(intent=intent)
        except LiveAutoViolation as exc:
            self._audit_denied(intent, f"wire-boundary re-check failed: {exc}")
            raise

    def _audit_denied(self, intent: OrderIntent, reason: str) -> None:
        if self._audit is not None:
            self._audit.record(
                "live_auto.order_denied",
                actor="live-auto-registry",
                target=intent.strategy_id,
                outcome="DENIED",
                metadata=_audit_metadata(
                    order_intent_id=intent.order_intent_id,
                    risk_decision_id=intent.risk_decision_id,
                    reason=reason,
                ),
            )

    def _active_record(self, intent: OrderIntent) -> LiveAutoStrategyRecord:
        record = self._store.get_strategy(intent.strategy_id)
        if record is None or not record.active or record.state is not StrategyState.LIVE_AUTO:
            raise LiveAutoViolation(
                f"strategy {intent.strategy_id!r} is not in the LIVE_AUTO lifecycle state"
            )
        return record

    def _assert_ceilings(self) -> None:
        """Defense in depth: an operator may tighten limits after promotion
        without restarting any process."""
        active = tuple(r for r in self._store.list_strategies() if r.active)
        if len(active) > self._config.max_strategies:
            raise LiveAutoViolation("LIVE_AUTO strategy ceiling exceeded")
        allocated = sum((r.capital_allocation for r in active), start=Decimal("0"))
        assert self._config.max_capital is not None  # assert_enabled guarantees it
        if allocated > self._config.max_capital:
            raise LiveAutoViolation("LIVE_AUTO capital ceiling exceeded")

    def _assert_loss_limit(self) -> None:
        assert self._config.max_loss is not None  # assert_enabled guarantees it
        if self._store.total_pnl() <= -self._config.max_loss:
            raise LiveAutoViolation(
                f"LIVE_AUTO global loss limit reached ({self._config.max_loss})"
            )

    def _assert_quantity_ceiling(self, intent: OrderIntent) -> None:
        if self._config.max_quantity is not None and intent.quantity > self._config.max_quantity:
            raise LiveAutoViolation(
                f"quantity {intent.quantity} exceeds the live quantity ceiling "
                f"{self._config.max_quantity}"
            )

    def _assert_wire_impl(self, *, intent: OrderIntent) -> None:
        self._config.assert_enabled()
        if intent.operating_mode is not OperatingMode.LIVE_AUTO:
            raise LiveAutoViolation("only LIVE_AUTO OrderIntents may use automated execution")
        self._active_record(intent)
        self._assert_ceilings()
        self._assert_loss_limit()
        self._assert_quantity_ceiling(intent)

    def _assert_submission_impl(
        self,
        *,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        price_context: PriceContext,
    ) -> LiveAutoStrategyRecord:
        self._config.assert_enabled()
        if intent.operating_mode is not OperatingMode.LIVE_AUTO:
            raise LiveAutoViolation("only LIVE_AUTO OrderIntents may use automated execution")

        record = self._active_record(intent)
        self._assert_ceilings()

        # Risk Engine is mandatory: the decision must exist, approve (or resize
        # with exact quantities) and hash-match the intent it was computed for.
        if risk_decision.decision is not RiskDecisionType.APPROVE and (
            risk_decision.decision is not RiskDecisionType.RESIZE
        ):
            raise LiveAutoViolation("LIVE_AUTO requires an APPROVE/RESIZE Risk Engine decision")
        if risk_decision.decision_id != intent.risk_decision_id:
            raise LiveAutoViolation(
                "Risk Engine decision does not match the OrderIntent's risk_decision_id"
            )
        if risk_decision.approved_quantity is None or risk_decision.approved_quantity != (
            intent.quantity
        ):
            raise LiveAutoViolation(
                "OrderIntent quantity does not match the Risk Engine approved_quantity"
            )
        if risk_decision.risk_amount is None:
            raise LiveAutoViolation("Risk Engine decision carries no risk_amount")
        if risk_decision.risk_amount > record.risk_budget:
            raise LiveAutoViolation(
                f"risk_amount {risk_decision.risk_amount} exceeds the strategy's "
                f"LIVE_AUTO risk budget {record.risk_budget}"
            )

        # Global LIVE_AUTO loss limit over the append-only realized-PnL ledger.
        self._assert_loss_limit()

        # MT4 local safety controls remain mandatory in automated mode.
        self._assert_quantity_ceiling(intent)
        quote_age: timedelta = self._clock.now() - price_context.observed_at
        if quote_age > self._config.max_quote_age:
            raise LiveAutoViolation(
                f"quote age {quote_age.total_seconds():.1f}s exceeds the "
                f"LIVE_AUTO freshness ceiling"
            )
        return record

    # ── Operator visibility ────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        """Serializable summary for the operator API."""
        return {
            "enabled": self._config.enabled,
            "max_strategies": self._config.max_strategies,
            "max_capital": (
                str(self._config.max_capital) if self._config.max_capital is not None else None
            ),
            "max_loss": str(self._config.max_loss) if self._config.max_loss is not None else None,
            "realized_pnl": str(self._store.total_pnl()),
            "strategies": [
                {
                    "strategy_id": record.strategy_id,
                    "strategy_version": record.strategy_version,
                    "from_state": record.from_state.value,
                    "state": record.state.value,
                    "risk_budget": str(record.risk_budget),
                    "capital_allocation": str(record.capital_allocation),
                    "promoted_by": record.promoted_by,
                    "promoted_at": record.promoted_at.isoformat(),
                    "active": record.active,
                    "demoted_by": record.demoted_by,
                    "demote_reason": record.demote_reason,
                }
                for record in self._store.list_strategies()
            ],
        }
