"""Fail-closed human authorization gate for ``LIVE_GATED`` execution.

Approval signatures are HMAC-SHA256 over a canonical payload.  The signing key must
come from a secret store; it is never persisted with the approval record.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from core.audit.audit import AuditLogger
from core.clock.clocks import Clock
from core.domain.enums import RiskDecisionType
from core.schemas.base import UtcDateTime
from core.schemas.trading import OrderIntent, RiskDecision
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApprovalRecord",
    "ApprovalStatus",
    "HumanApprovalGate",
    "InMemoryApprovalStore",
    "KillScope",
    "LiveGateConfig",
    "LiveGateViolation",
    "PriceContext",
]


class LiveGateViolation(RuntimeError):
    """The live order is not authorized to cross the broker boundary."""


class ApprovalStatus(StrEnum):
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    APPROVED = "APPROVED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"
    REJECTED = "REJECTED"


class KillScope(StrEnum):
    STRATEGY = "STRATEGY"
    INSTRUMENT = "INSTRUMENT"
    PORTFOLIO = "PORTFOLIO"
    EMERGENCY = "EMERGENCY"


class PriceContext(BaseModel):
    """The exact market observation displayed to and approved by the human."""

    model_config = ConfigDict(frozen=True)
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    observed_at: UtcDateTime

    @property
    def midpoint(self) -> Decimal:
        return (self.bid + self.ask) / Decimal(2)


@dataclass(frozen=True, slots=True)
class LiveGateConfig:
    approval_ttl: timedelta = timedelta(seconds=30)
    max_price_drift_bps: Decimal = Decimal("10")
    max_quote_age: timedelta = timedelta(seconds=5)
    broker_demo: bool = False
    max_live_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        if self.approval_ttl <= timedelta(0) or self.max_quote_age <= timedelta(0):
            raise ValueError("approval and quote lifetimes must be positive")
        if self.max_price_drift_bps < 0:
            raise ValueError("max_price_drift_bps must be non-negative")
        if self.max_live_quantity is not None and self.max_live_quantity <= 0:
            raise ValueError("max_live_quantity must be positive")


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: UUID
    order_intent_id: UUID
    risk_decision_id: UUID
    strategy_id: str
    strategy_version: str
    instrument_id: str
    intent_hash: str
    price_context: PriceContext
    requested_at: datetime
    expires_at: datetime
    status: ApprovalStatus
    approver_id: str | None = None
    approved_at: datetime | None = None
    consumed_at: datetime | None = None
    signature: str | None = None
    invalidation_reason: str | None = None


class ApprovalStore(Protocol):
    def get(self, order_intent_id: UUID) -> ApprovalRecord | None: ...
    def put(self, record: ApprovalRecord) -> ApprovalRecord: ...
    def put_if_absent(self, record: ApprovalRecord) -> bool: ...
    def compare_and_put(self, expected: ApprovalStatus, record: ApprovalRecord) -> bool: ...
    def active_kills(self) -> set[tuple[KillScope, str | None]]: ...
    def set_kill(
        self, scope: KillScope, target: str | None, actor: str, reason: str, at: datetime
    ) -> None: ...
    def clear_kill(
        self,
        scope: KillScope,
        target: str | None,
        actor: str,
        reason: str,
        at: datetime,
    ) -> None: ...


class InMemoryApprovalStore:
    """Thread-safe test/dev store. Production wiring should use transactional storage."""

    def __init__(self) -> None:
        self._records: dict[UUID, ApprovalRecord] = {}
        self._kills: dict[tuple[KillScope, str | None], tuple[str, str, datetime]] = {}
        self._lock = RLock()

    def get(self, order_intent_id: UUID) -> ApprovalRecord | None:
        with self._lock:
            return self._records.get(order_intent_id)

    def put(self, record: ApprovalRecord) -> ApprovalRecord:
        with self._lock:
            self._records[record.order_intent_id] = record
            return record

    def put_if_absent(self, record: ApprovalRecord) -> bool:
        with self._lock:
            if record.order_intent_id in self._records:
                return False
            self._records[record.order_intent_id] = record
            return True

    def compare_and_put(self, expected: ApprovalStatus, record: ApprovalRecord) -> bool:
        with self._lock:
            current = self._records.get(record.order_intent_id)
            if current is None or current.status is not expected:
                return False
            self._records[record.order_intent_id] = record
            return True

    def active_kills(self) -> set[tuple[KillScope, str | None]]:
        with self._lock:
            return set(self._kills)

    def set_kill(
        self, scope: KillScope, target: str | None, actor: str, reason: str, at: datetime
    ) -> None:
        with self._lock:
            self._kills[(scope, target)] = (actor, reason, at)

    def clear_kill(
        self,
        scope: KillScope,
        target: str | None,
        actor: str,
        reason: str,
        at: datetime,
    ) -> None:
        del actor, reason, at
        with self._lock:
            self._kills.pop((scope, target), None)


class HumanApprovalGate:
    """State machine and cryptographic verifier for human-gated live orders."""

    def __init__(
        self,
        *,
        store: ApprovalStore,
        clock: Clock,
        signing_key: bytes,
        config: LiveGateConfig,
        audit: AuditLogger | None = None,
        demo_account_attestor: Callable[[], bool] | None = None,
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("approval signing key must contain at least 32 bytes")
        if config.max_live_quantity is None and (
            not config.broker_demo or demo_account_attestor is None
        ):
            raise ValueError(
                "LIVE_GATED requires broker demo attestation or an explicit tiny max_live_quantity"
            )
        self._store = store
        self._clock = clock
        self._key = signing_key
        self._config = config
        self._audit = audit
        self._demo_account_attestor = demo_account_attestor
        self._lock = RLock()

    def request_approval(self, intent: OrderIntent, price_context: PriceContext) -> ApprovalRecord:
        now = self._clock.now()
        self._assert_exposure(intent)
        self._assert_no_kill(intent)
        self._assert_quote_fresh(price_context, now)
        if intent.valid_until is not None and now >= intent.valid_until:
            raise LiveGateViolation("OrderIntent is stale")
        expires_at = now + self._config.approval_ttl
        if intent.valid_until is not None:
            expires_at = min(expires_at, intent.valid_until)
        record = ApprovalRecord(
            approval_id=uuid4(),
            order_intent_id=intent.order_intent_id,
            risk_decision_id=intent.risk_decision_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            instrument_id=intent.instrument_id,
            intent_hash=self._intent_hash(intent),
            price_context=price_context,
            requested_at=now,
            expires_at=expires_at,
            status=ApprovalStatus.WAITING_FOR_HUMAN,
        )
        if not self._store.put_if_absent(record):
            raise LiveGateViolation("an approval lifecycle already exists for this OrderIntent")
        stored = record
        self._audit_record("live_gate.approval_requested", "system", stored)
        return stored

    def get_approval(self, order_intent_id: UUID) -> ApprovalRecord | None:
        return self._store.get(order_intent_id)

    def assert_consumed_authorization(self, intent: OrderIntent) -> None:
        """Second boundary check used by the MT4 client immediately before send."""
        record = self._required(intent.order_intent_id)
        now = self._clock.now()
        if record.status is not ApprovalStatus.CONSUMED:
            raise LiveGateViolation("MT4 submission lacks a consumed human approval")
        if now >= record.expires_at:
            raise LiveGateViolation("MT4 submission approval expired")
        if not self._matches_intent(record, intent):
            raise LiveGateViolation("MT4 submission does not match the approved OrderIntent")
        if record.signature is None or not hmac.compare_digest(
            record.signature, self._signature(record)
        ):
            raise LiveGateViolation("MT4 submission approval signature verification failed")
        active = (
            (KillScope.EMERGENCY, None),
            (KillScope.PORTFOLIO, None),
            (KillScope.STRATEGY, record.strategy_id),
            (KillScope.INSTRUMENT, record.instrument_id),
        )
        if any(key in self._store.active_kills() for key in active):
            raise LiveGateViolation("an active kill switch blocks MT4 submission")

    def approve(self, order_intent_id: UUID, *, approver_id: str) -> ApprovalRecord:
        if not approver_id.strip():
            raise LiveGateViolation("an authenticated approver identity is required")
        with self._lock:
            record = self._required(order_intent_id)
            now = self._clock.now()
            if record.status is not ApprovalStatus.WAITING_FOR_HUMAN:
                raise LiveGateViolation(f"approval is not waiting for a human: {record.status}")
            if now >= record.expires_at:
                self._store.put(replace(record, status=ApprovalStatus.EXPIRED))
                raise LiveGateViolation("approval request expired")
            approved = replace(
                record,
                status=ApprovalStatus.APPROVED,
                approver_id=approver_id.strip(),
                approved_at=now,
            )
            approved = replace(approved, signature=self._signature(approved))
            if not self._store.compare_and_put(ApprovalStatus.WAITING_FOR_HUMAN, approved):
                raise LiveGateViolation("approval changed concurrently")
            stored = approved
            self._audit_record("live_gate.approved", approver_id.strip(), stored)
            return stored

    def reject(self, order_intent_id: UUID, *, approver_id: str) -> ApprovalRecord:
        record = self._required(order_intent_id)
        if record.status is not ApprovalStatus.WAITING_FOR_HUMAN:
            raise LiveGateViolation(f"approval is not waiting for a human: {record.status}")
        return self._store.put(
            replace(record, status=ApprovalStatus.REJECTED, approver_id=approver_id.strip())
        )

    def revalidate(
        self,
        order_intent_id: UUID,
        *,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        price_context: PriceContext,
    ) -> ApprovalRecord:
        record = self._required(order_intent_id)
        if record.status is not ApprovalStatus.REVALIDATION_REQUIRED:
            raise LiveGateViolation("risk revalidation was not requested")
        now = self._clock.now()
        self._assert_quote_fresh(price_context, now)
        if intent.order_intent_id != record.order_intent_id:
            raise LiveGateViolation("revalidated OrderIntent id does not match")
        if intent.risk_decision_id != risk_decision.decision_id:
            raise LiveGateViolation("revalidated OrderIntent is not bound to the risk decision")
        if (
            risk_decision.decision is not RiskDecisionType.REJECT
            and risk_decision.approved_quantity != intent.quantity
        ):
            raise LiveGateViolation("revalidated quantity does not match risk approval")
        if risk_decision.decision is RiskDecisionType.REJECT:
            return self._store.put(
                replace(record, status=ApprovalStatus.REJECTED, invalidation_reason="risk rejected")
            )
        return self._store.put(
            replace(
                record,
                approval_id=uuid4(),
                risk_decision_id=risk_decision.decision_id,
                price_context=price_context,
                intent_hash=self._intent_hash(intent),
                requested_at=now,
                expires_at=now + self._config.approval_ttl,
                status=ApprovalStatus.WAITING_FOR_HUMAN,
                approver_id=None,
                approved_at=None,
                consumed_at=None,
                signature=None,
                invalidation_reason=None,
            )
        )

    def consume(self, intent: OrderIntent, price_context: PriceContext) -> ApprovalRecord:
        """Atomically verify and consume approval immediately before wire transmission."""
        with self._lock:
            self._assert_exposure(intent)
            self._assert_no_kill(intent)
            record = self._required(intent.order_intent_id)
            now = self._clock.now()
            if record.status is ApprovalStatus.CONSUMED:
                raise LiveGateViolation("approval was already consumed")
            if record.status is not ApprovalStatus.APPROVED:
                raise LiveGateViolation("explicit human approval is required")
            if now >= record.expires_at:
                self._store.put(replace(record, status=ApprovalStatus.EXPIRED))
                raise LiveGateViolation("approval expired")
            self._assert_quote_fresh(price_context, now)
            if not self._matches_intent(record, intent):
                raise LiveGateViolation("approved order does not match the current OrderIntent")
            if record.signature is None or not hmac.compare_digest(
                record.signature, self._signature(record)
            ):
                raise LiveGateViolation("approval signature verification failed")
            if self._materially_changed(record.price_context, price_context):
                self._store.put(
                    replace(
                        record,
                        status=ApprovalStatus.REVALIDATION_REQUIRED,
                        invalidation_reason="material price change",
                    )
                )
                raise LiveGateViolation("market changed materially; risk revalidation is required")
            consumed = replace(record, status=ApprovalStatus.CONSUMED, consumed_at=now)
            if not self._store.compare_and_put(ApprovalStatus.APPROVED, consumed):
                raise LiveGateViolation("approval was already consumed")
            stored = consumed
            self._audit_record("live_gate.approval_consumed", "execution-engine", stored)
            return stored

    def activate_kill(
        self, scope: KillScope, *, actor: str, reason: str, target: str | None = None
    ) -> None:
        if scope in (KillScope.STRATEGY, KillScope.INSTRUMENT) and not target:
            raise ValueError(f"{scope.value} kill requires a target")
        self._store.set_kill(scope, target, actor, reason, self._clock.now())
        if self._audit is not None:
            self._audit.record(
                "live_gate.kill_activated",
                actor=actor,
                target=target or scope.value,
                metadata={"scope": scope.value, "reason": reason},
            )

    def clear_kill(
        self,
        scope: KillScope,
        *,
        actor: str,
        reason: str,
        target: str | None = None,
    ) -> None:
        self._store.clear_kill(scope, target, actor, reason, self._clock.now())
        if self._audit is not None:
            self._audit.record(
                "live_gate.kill_cleared",
                actor=actor,
                target=target or scope.value,
                metadata={"scope": scope.value, "reason": reason},
            )

    def _required(self, order_intent_id: UUID) -> ApprovalRecord:
        record = self._store.get(order_intent_id)
        if record is None:
            raise LiveGateViolation("explicit human approval is required")
        return record

    def _assert_no_kill(self, intent: OrderIntent) -> None:
        active = (
            (KillScope.EMERGENCY, None),
            (KillScope.PORTFOLIO, None),
            (KillScope.STRATEGY, intent.strategy_id),
            (KillScope.INSTRUMENT, intent.instrument_id),
        )
        if any(key in self._store.active_kills() for key in active):
            raise LiveGateViolation("an active kill switch blocks this order")

    def _assert_exposure(self, intent: OrderIntent) -> None:
        cap = self._config.max_live_quantity
        demo_attested = (
            self._config.broker_demo
            and self._demo_account_attestor is not None
            and self._demo_account_attestor()
        )
        if not demo_attested and (cap is None or intent.quantity > cap):
            raise LiveGateViolation("order exceeds deliberately tiny live exposure")
        if cap is not None and intent.quantity > cap:
            raise LiveGateViolation("order exceeds configured live exposure")

    def _assert_quote_fresh(self, price: PriceContext, now: datetime) -> None:
        if price.ask < price.bid:
            raise LiveGateViolation("invalid price context: ask is below bid")
        age = now - price.observed_at
        if age < timedelta(0) or age > self._config.max_quote_age:
            raise LiveGateViolation("price context is stale")

    def _materially_changed(self, approved: PriceContext, current: PriceContext) -> bool:
        drift = abs(current.midpoint - approved.midpoint) / approved.midpoint * Decimal(10_000)
        return drift > self._config.max_price_drift_bps

    @staticmethod
    def _matches_intent(record: ApprovalRecord, intent: OrderIntent) -> bool:
        return (
            record.order_intent_id == intent.order_intent_id
            and record.risk_decision_id == intent.risk_decision_id
            and record.strategy_id == intent.strategy_id
            and record.strategy_version == intent.strategy_version
            and record.instrument_id == intent.instrument_id
            and hmac.compare_digest(record.intent_hash, HumanApprovalGate._intent_hash(intent))
        )

    def _signature(self, record: ApprovalRecord) -> str:
        if record.approver_id is None or record.approved_at is None:
            raise LiveGateViolation("cannot sign an incomplete approval")
        payload = {
            "approval_id": str(record.approval_id),
            "order_intent_id": str(record.order_intent_id),
            "risk_decision_id": str(record.risk_decision_id),
            "strategy_id": record.strategy_id,
            "strategy_version": record.strategy_version,
            "instrument_id": record.instrument_id,
            "intent_hash": record.intent_hash,
            "price_context": {
                "bid": str(record.price_context.bid),
                "ask": str(record.price_context.ask),
                "observed_at": record.price_context.observed_at.isoformat(),
            },
            "requested_at": record.requested_at.isoformat(),
            "approved_at": record.approved_at.isoformat(),
            "expires_at": record.expires_at.isoformat(),
            "approver_id": record.approver_id,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._key, canonical, hashlib.sha256).hexdigest()

    @staticmethod
    def _intent_hash(intent: OrderIntent) -> str:
        return hashlib.sha256(intent.to_json_bytes()).hexdigest()

    def _audit_record(self, action: str, actor: str, record: ApprovalRecord) -> None:
        if self._audit is None:
            return
        self._audit.record(
            action,
            actor=actor,
            target=str(record.order_intent_id),
            metadata={
                "approval_id": str(record.approval_id),
                "order_intent_id": str(record.order_intent_id),
                "risk_decision_id": str(record.risk_decision_id),
                "strategy_version": record.strategy_version,
                "price_context": record.price_context.model_dump(mode="json"),
                "requested_at": record.requested_at.isoformat(),
                "approved_at": record.approved_at.isoformat() if record.approved_at else None,
                "expires_at": record.expires_at.isoformat(),
                "signature": record.signature,
                "status": record.status.value,
            },
        )
