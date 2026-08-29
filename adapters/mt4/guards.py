"""Command gate: expiration, duplicate detection, sequence validation (ADR-0020).

Pure, deterministic, testable without sockets. The emulator runs this gate on
every incoming command; the MQL4 EA must implement the same checks in the same
order (see ``mt4/protocol/README.md`` §Validation order).

Check order (frozen in the spec):

1. schema validation (``parse_message``)
2. protocol_version compatibility (model validator)
3. checksum (transport integrity)
4. command expiration (``expires_at``)
5. duplicate detection (``order_intent_id`` + content fingerprint)
6. sequence validation (per-``strategy_id`` strict monotonic)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.clock.clocks import Clock
from core.schemas.base import ensure_utc

from adapters.mt4.errors import Mt4ErrorCode, ProtocolErrorDetail
from adapters.mt4.ledger import IntentLedger, IntentRecord, SequenceTracker, build_intent_record
from adapters.mt4.protocol import (
    CommandMessage,
    ModifyOrderCommand,
    ReconciliationRequestCommand,
    WireMessage,
)

__all__ = ["CommandGate", "GateOutcome"]


@dataclass(frozen=True)
class GateOutcome:
    """Verdict of the command gate for one incoming command."""

    accepted: bool
    error: ProtocolErrorDetail | None = None
    #: Original reply to replay when this is a recognized duplicate.
    replay: WireMessage | None = None
    #: Expected next sequence in the command's namespace (diagnostics).
    expected_sequence: int | None = None


class CommandGate:
    """Validates incoming commands: expiry → duplicates → sequence."""

    def __init__(self, clock: Clock, ledger: IntentLedger | None = None) -> None:
        self._clock = clock
        self._ledger = ledger or IntentLedger()
        self._sequences = SequenceTracker()

    @property
    def ledger(self) -> IntentLedger:
        return self._ledger

    def sequences_snapshot(self) -> dict[str, int]:
        """Per-strategy last-accepted sequences, for restart resync (INV-6)."""
        return self._sequences.snapshot()

    def evaluate(self, command: CommandMessage) -> GateOutcome:
        """Validate one command without mutating state.

        A True ``accepted`` outcome means the caller should execute the command
        and then call :meth:`record`. ``replay`` is set for exact duplicates.
        """
        now = self._clock.now()

        # Reconciliation is a stateless query: no idempotency or sequence
        # semantics, and it never advances a namespace (restarts must always
        # be able to reconcile before resyncing, INV-6).
        if isinstance(command, ReconciliationRequestCommand):
            return GateOutcome(accepted=True)

        # 4. Command expiration — checked before anything else: an expired
        # command is dead even if it is a faithful duplicate.
        if command.expires_at is not None and ensure_utc(command.expires_at) <= now:
            return GateOutcome(
                accepted=False,
                error=self._error(command, Mt4ErrorCode.COMMAND_EXPIRED, now, "command expired"),
                expected_sequence=self._sequences.expected(command.strategy_id),
            )

        # 5. Duplicate detection, scoped by (order_intent_id, command_type).
        # submit/cancel are one-shot per intent; modify may repeat with new
        # fields (each amendment is a new command).
        intent_id = command.order_intent_id
        if intent_id is not None:
            record = self._ledger.lookup(intent_id, command.message_type.value)
            if record is not None:
                if record.fingerprint == command.fingerprint():
                    return GateOutcome(
                        accepted=False,
                        replay=record.original_reply,
                        expected_sequence=self._sequences.expected(command.strategy_id),
                    )
                if isinstance(command, ModifyOrderCommand):
                    pass  # a second amendment with new fields is legitimate
                else:
                    return GateOutcome(
                        accepted=False,
                        error=self._error(
                            command,
                            Mt4ErrorCode.INTENT_CONFLICT,
                            now,
                            f"order_intent_id {intent_id} reused with different fields",
                        ),
                        expected_sequence=self._sequences.expected(command.strategy_id),
                    )

        # 6. Sequence validation: strict monotonic per strategy namespace.
        if not self._sequences.is_valid_next(command.strategy_id, command.sequence):
            return GateOutcome(
                accepted=False,
                error=self._error(
                    command,
                    Mt4ErrorCode.SEQUENCE_VIOLATION,
                    now,
                    f"expected sequence {self._sequences.expected(command.strategy_id)}",
                ),
                expected_sequence=self._sequences.expected(command.strategy_id),
            )

        return GateOutcome(accepted=True)

    def record(self, command: CommandMessage, reply: WireMessage) -> None:
        """Persist the outcome of an accepted command (idempotency memory)."""
        if isinstance(command, ReconciliationRequestCommand):
            return  # stateless query — nothing to remember
        intent_id = command.order_intent_id
        if intent_id is not None:
            record: IntentRecord = build_intent_record(command)
            # Submit/cancel records are immutable; a newer modify amendment
            # replaces the previous one (replay only matches exact content).
            self._ledger.record(record, allow_replace=isinstance(command, ModifyOrderCommand))
            self._ledger.attach_reply(intent_id, command.message_type.value, reply)
        self._sequences.accept(command.strategy_id, command.sequence)

    def _error(
        self,
        command: CommandMessage,
        code: Mt4ErrorCode,
        now: datetime,
        message: str,
    ) -> ProtocolErrorDetail:
        return ProtocolErrorDetail.create(
            code,
            message,
            detail=f"sequence={command.sequence} strategy={command.strategy_id}",
            trace_id=command.trace_id,
            order_intent_id=command.order_intent_id,
            symbol=command.symbol,
            sequence=command.sequence,
            now=now,
        )
