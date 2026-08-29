"""Idempotency ledger and per-strategy sequence tracking (ADR-0020).

The ledger is the receiver-side memory that makes the protocol safe:

- ``IntentLedger`` — remembers every ``order_intent_id`` together with the
  content fingerprint of the first command that used it and the outcome that
  was returned. Re-delivery of the same intent re-acks the stored outcome;
  the same intent with different fields is an INTENT_CONFLICT. This is what
  guarantees "the same order_intent_id sent 100 times never produces more
  than one trade" (Phase 6 DoD).
- ``SequenceTracker`` — enforces strict monotonic per-strategy sequences so
  lost/duplicated/gap commands are detected instead of silently reordered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from adapters.mt4.protocol import CommandMessage, WireMessage

__all__ = ["IntentLedger", "IntentRecord", "SequenceTracker"]


@dataclass(frozen=True)
class IntentRecord:
    """What the bridge remembers about one order_intent_id."""

    order_intent_id: UUID
    fingerprint: str
    command_type: str
    sequence: int
    strategy_id: str
    symbol: str | None
    #: Serialized outcome returned for the original command (replay source).
    original_reply: WireMessage | None = None


@dataclass
class IntentLedger:
    """In-memory idempotency store, keyed by (order_intent_id, command_type).

    Keying includes the command type because cancel/modify legitimately reuse
    an intent id: a submit is one-shot per intent, a cancel is one-shot per
    intent, but modify may repeat with different fields (multiple amendments).
    """

    _records: dict[tuple[UUID, str], IntentRecord] = field(default_factory=dict)

    def lookup(self, order_intent_id: UUID, command_type: str) -> IntentRecord | None:
        return self._records.get((order_intent_id, command_type))

    def has_submit(self, order_intent_id: UUID) -> bool:
        return (order_intent_id, "submit_order") in self._records

    def record(self, record: IntentRecord, *, allow_replace: bool = False) -> None:
        """Register an intent. Submit/cancel records are immutable; modify
        records may be replaced by a newer amendment."""
        key = (record.order_intent_id, record.command_type)
        if key in self._records and not allow_replace:
            raise ValueError(f"intent {key} already recorded")
        self._records[key] = record

    def attach_reply(self, order_intent_id: UUID, command_type: str, reply: WireMessage) -> None:
        key = (order_intent_id, command_type)
        record = self._records.get(key)
        if record is None:
            raise ValueError(f"intent {key} not in ledger")
        # IntentRecord is frozen: replace with a copy carrying the reply.
        self._records[key] = IntentRecord(
            order_intent_id=record.order_intent_id,
            fingerprint=record.fingerprint,
            command_type=record.command_type,
            sequence=record.sequence,
            strategy_id=record.strategy_id,
            symbol=record.symbol,
            original_reply=reply,
        )

    def submitted_intent_ids(self) -> tuple[UUID, ...]:
        return tuple(
            intent_id
            for (intent_id, command_type) in self._records
            if command_type == "submit_order"
        )

    def reset(self) -> None:
        self._records.clear()


@dataclass
class SequenceTracker:
    """Strict monotonic sequence validation per ``strategy_id`` namespace.

    Sequences start at 1 within each namespace. A command whose sequence is
    not exactly ``last + 1`` is refused unless the command is a recognized
    duplicate of an already-recorded intent (handled by the gate).
    """

    _last: dict[str, int] = field(default_factory=dict)

    def last(self, strategy_id: str) -> int:
        return self._last.get(strategy_id, 0)

    def expected(self, strategy_id: str) -> int:
        return self.last(strategy_id) + 1

    def accept(self, strategy_id: str, sequence: int) -> None:
        """Record a newly accepted sequence (must equal expected)."""
        if sequence != self.expected(strategy_id):
            raise ValueError(
                f"sequence {sequence} not accepted for {strategy_id!r}; "
                f"expected {self.expected(strategy_id)}"
            )
        self._last[strategy_id] = sequence

    def is_valid_next(self, strategy_id: str, sequence: int) -> bool:
        return sequence == self.expected(strategy_id)

    def snapshot(self) -> dict[str, int]:
        """Per-namespace last-accepted sequences (reconciliation payload)."""
        return dict(self._last)

    def reset(self, strategy_id: str | None = None) -> None:
        if strategy_id is None:
            self._last.clear()
        else:
            self._last.pop(strategy_id, None)


def build_intent_record(command: CommandMessage) -> IntentRecord:
    if command.order_intent_id is None:
        raise ValueError("order-bearing commands require order_intent_id")
    return IntentRecord(
        order_intent_id=command.order_intent_id,
        fingerprint=command.fingerprint(),
        command_type=command.message_type.value,
        sequence=command.sequence,
        strategy_id=command.strategy_id,
        symbol=command.symbol,
    )
