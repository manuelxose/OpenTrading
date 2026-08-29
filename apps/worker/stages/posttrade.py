"""Post-trade stage: closed-and-reconciled trade → full postmortem (Phase 7).

Closes the loop (architecture §15/§17):

1. **Reconciliation gate** — a postmortem runs only when every order referenced
   by the outcome has reached a terminal state (``CLOSED`` / ``RECONCILED`` /
   ``REVIEWED``) in the execution store (INV-6). If the trade is not yet
   definitively closed-and-reconciled the stage *fails* (never silently
   succeeds): the message stays unacked and is redelivered until reconciliation
   catches up.
2. **Deterministic analysis** — ``engines.posttrade`` computes the canonical
   metrics (PnL, fees, slippage, R multiple, alpha, MAE, MFE, holding time,
   entry/exit efficiency, calibration, prediction error, regime) and evaluates
   QuantSignal / LLMSignal / FusedSignal / RiskDecision / execution quality
   independently, then compares expected vs actual.
3. **Four sink writes**:
   - canonical metrics → PostgreSQL (``posttrade_reviews``);
   - full audit artifact → MinIO (``posttrade-artifacts`` bucket);
   - semantic lesson → Graphiti temporal memory (LONG_TERM episode);
   - human-readable note → Obsidian vault.
4. **Terminal bookkeeping** — order records → REVIEWED; trade lifecycles →
   REVIEWED; emits ``postmortem.completed`` / ``memory.episode.created``.

Post-trade analysis never modifies live risk limits: this module (and the whole
``engines.posttrade`` tree) only *reads* the RiskDecision produced at entry
(INV-1).
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID, uuid5

from core.domain.enums import MemoryLayer, OrderState, PipelineStageName, TradeLifecycleState
from core.schemas import (
    FusedSignal,
    LLMSignal,
    MemoryContext,
    PostTradeReview,
    QuantSignal,
    RiskDecision,
    TradeOutcome,
    TradeProposal,
)
from core.schemas.events import DomainEvent
from core.schemas.memory import EntityRef, MemoryEpisode, RelationRef
from core.schemas.pipeline import TradeLifecycle
from core.schemas.posttrade import PostTradeReviewRecord
from core.schemas.trading import (
    AttributionAnalysis,
    ExecutionAnalysis,
    QuantEvaluation,
    RiskEvaluation,
    ThesisEvaluation,
)
from engines.posttrade.analysis import AnalysisContext, AnalysisResult, analyze
from engines.posttrade.artifacts import artifact_key, build_artifact
from engines.posttrade.notes import note_path, render_note
from pydantic import BaseModel

from apps.worker.lifecycle import transition_chain
from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["PostTradeReconciliationPendingError", "PosttradeStage"]

_PRODUCER = "apps.worker.posttrade"

_ModelT = TypeVar("_ModelT", bound=BaseModel)

#: Deterministic review id per trade (replay-safe postmortems).
_REVIEW_NS = UUID("6f9f4d2c-9b2f-4c8a-8e5a-2d3c4b5a6f7e")

#: Execution-store states that certify "definitively closed and reconciled".
_RECONCILED_TERMINAL = (OrderState.CLOSED, OrderState.RECONCILED, OrderState.REVIEWED)


class PostTradeReconciliationPendingError(RuntimeError):
    """The trade is not yet definitively closed-and-reconciled (INV-6).

    Raised on purpose: a stage failure leaves the message unacked, so the bus
    redelivers it until the execution store catches up. The stage must never
    mark a pending postmortem as SUCCEEDED.
    """


class PosttradeStage(Stage):
    name = PipelineStageName.POSTTRADE
    consumes = ("trade.closed",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        outcome = TradeOutcome.model_validate(event.payload)
        trace_id = event.trace_id
        assert trace_id is not None
        now = rt.clock.now()
        events: list[DomainEvent] = []

        # ── 1. reconciliation gate (fail → redelivery, never silent skip) ─────
        self._require_reconciled(rt, outcome, trace_id)

        review_id = uuid5(_REVIEW_NS, str(outcome.trade_id))
        store = rt.extras["posttrade_store"]
        existing = store.get_by_trade(outcome.trade_id)
        if existing is not None:
            # Crash recovery: the review was persisted; re-emit the canonical
            # event and resume idempotent terminal bookkeeping so a crash
            # between persistence and finalization cannot strand the trade.
            review = PostTradeReview.model_validate(existing.review_payload)
            self._complete_bookkeeping(rt, outcome, trace_id)
            return [self.make_event(rt, "postmortem.completed", review, trace_id=trace_id)]

        # ── 2. reconstruct the entry decision chain ────────────────────────────
        entry = self._entry_lifecycle(rt, outcome)
        context = self._analysis_context(rt, outcome, entry)
        result = analyze(context)
        strategy_id = entry.strategy_id if entry is not None else rt.config.strategy_id
        strategy_version = (
            entry.strategy_version if entry is not None else rt.config.strategy_version
        )

        review = PostTradeReview(
            review_id=review_id,
            trade_id=outcome.trade_id,
            execution=ExecutionAnalysis(
                slippage=result.metrics.slippage,
                fees=result.metrics.fees,
                latency_ms=None,
                fill_quality=result.execution_quality.fill_quality or "paper",
            ),
            attribution=AttributionAnalysis(
                alpha_contribution=result.metrics.alpha_pct,
                sources=dict(result.expected_vs_actual),
            ),
            thesis=ThesisEvaluation(
                summary=result.thesis_summary,
                verdict=result.verdict,
                confidence=result.verdict_confidence,
            ),
            quant=self._quant_evaluation(result),
            risk=RiskEvaluation(
                limits_respected=result.risk_quality.limits_respected,
                mae_used=result.metrics.mae_pct,
                notes=result.risk_quality.notes,
            ),
            metrics=result.metrics,
            signal_quality=result.signal_quality,
            risk_quality=result.risk_quality,
            execution_quality=result.execution_quality,
            expected_vs_actual=result.expected_vs_actual,
            lessons=result.lessons,
            postmortem_completed=True,
            trace_id=trace_id,
            produced_at=now,
            provenance=rt.provenance(_PRODUCER, now),
        )
        research_trace_id = entry.trace_id if entry is not None else trace_id
        with rt.telemetry.observation(
            trace_id=research_trace_id,
            name="trade.postmortem",
            as_type="evaluator",
            metadata={
                "component": "posttrade",
                "instrument_id": outcome.instrument_id,
                "status": "completed",
            },
            input={"trade_id": str(outcome.trade_id), "closing_trace_id": str(trace_id)},
        ) as observation:
            observation.update(
                output={
                    "review_id": str(review_id),
                    "verdict": result.verdict,
                    "pnl_net": str(result.metrics.pnl_net),
                    "r_multiple": result.metrics.r_multiple,
                }
            )

        record = PostTradeReviewRecord(
            review_id=review_id,
            trade_id=outcome.trade_id,
            position_id=outcome.position_id,
            instrument_id=outcome.instrument_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            direction=outcome.direction,
            opened_at=outcome.opened_at,
            closed_at=outcome.closed_at,
            exit_reason=outcome.exit_reason,
            metrics=result.metrics,
            verdict=result.verdict,
            postmortem_completed=True,
            review_payload=review.canonical_dict(),
            trace_id=trace_id,
            created_at=now,
        )

        # ── 3. side-effect sinks (failures audit but never block the postmortem) ──
        artifact_key_value = self._write_artifact(rt, record, outcome, review_id)
        vault_path_value = self._write_vault_note(rt, record, outcome, review_id)
        episode = self._ingest_lesson(rt, outcome, result, review_id, strategy_id, trace_id, now)
        if episode is not None:
            events.append(self.make_event(rt, "memory.episode.created", episode, trace_id=trace_id))

        review = review.model_copy(
            update={"artifact_ref": artifact_key_value, "vault_path": vault_path_value}
        )
        record = record.model_copy(
            update={
                "artifact_key": artifact_key_value,
                "vault_path": vault_path_value,
                "episode_id": episode.episode_id if episode is not None else None,
                "review_payload": review.canonical_dict(),
            }
        )

        # ── canonical metrics in PostgreSQL (DoD backbone; failures retry) ─────
        store.save_review(record)
        rt.audit.record(
            "postmortem.completed",
            target=str(outcome.trade_id),
            trace_id=trace_id,
            metadata={
                "review_id": str(review_id),
                "verdict": result.verdict,
                "r_multiple": result.metrics.r_multiple,
                "artifact_key": artifact_key_value,
                "vault_path": vault_path_value,
            },
        )
        events.append(self.make_event(rt, "postmortem.completed", review, trace_id=trace_id))

        # ── 4. terminal bookkeeping ─────────────────────────────────────────────
        self._complete_bookkeeping(rt, outcome, trace_id, entry=entry)
        return events

    def _complete_bookkeeping(
        self,
        rt: StageRuntime,
        outcome: TradeOutcome,
        trace_id: UUID,
        *,
        entry: TradeLifecycle | None = None,
    ) -> None:
        """Idempotently finish lifecycle state after canonical persistence."""
        for raw in outcome.order_intent_ids:
            with suppress(Exception):  # already reviewed / unknown intent
                rt.extras["applier"].record_reviewed(UUID(raw))

        closing = rt.store.get_lifecycle_by_trace(trace_id)
        if closing is not None and closing.state in (
            TradeLifecycleState.POSITION_CLOSED,
            TradeLifecycleState.ORDER_CREATED,
        ):
            transition_chain(
                rt,
                trace_id,
                (TradeLifecycleState.POSITION_CLOSED, TradeLifecycleState.REVIEWED),
                fields={"trade_id": outcome.trade_id},
            )
        entry = entry or self._entry_lifecycle(rt, outcome)
        if entry is not None and entry.state is TradeLifecycleState.POSITION_OPEN:
            transition_chain(
                rt,
                entry.trace_id,
                (TradeLifecycleState.POSITION_CLOSED, TradeLifecycleState.REVIEWED),
                fields={"trade_id": outcome.trade_id},
            )

        if outcome.position_id is not None:
            rt.ledger.clear_price_path(outcome.position_id)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _require_reconciled(self, rt: StageRuntime, outcome: TradeOutcome, trace_id: UUID) -> None:
        """Certify the trade is definitively closed-and-reconciled (INV-6)."""
        if not outcome.order_intent_ids:
            return  # nothing to reconcile against (e.g. adopted positions)
        pending: list[str] = []
        for raw in outcome.order_intent_ids:
            record = rt.execution_store.get_order(UUID(raw))
            if record is None or record.state not in _RECONCILED_TERMINAL:
                pending.append(raw)
        if pending:
            rt.audit.record(
                "posttrade.reconciliation.pending",
                target=str(outcome.trade_id),
                trace_id=trace_id,
                outcome="PENDING",
                metadata={"pending_order_intent_ids": pending},
            )
            raise PostTradeReconciliationPendingError(
                f"trade {outcome.trade_id} is not yet closed-and-reconciled: "
                f"pending orders {pending}"
            )

    def _entry_lifecycle(self, rt: StageRuntime, outcome: TradeOutcome) -> TradeLifecycle | None:
        """The entry-side lifecycle matched by position id (INV-6 audit path)."""
        if outcome.position_id is None:
            return None
        for lifecycle in rt.store.list_lifecycles():
            if lifecycle.position_id != outcome.position_id:
                continue
            if lifecycle.direction is outcome.direction:
                return lifecycle
        return None

    def _analysis_context(
        self, rt: StageRuntime, outcome: TradeOutcome, entry: TradeLifecycle | None
    ) -> AnalysisContext:
        """Reassemble the captured decision chain for the entry trace."""
        fragments: dict[str, dict[str, Any]] = {}
        if entry is not None:
            context_record = rt.store.get_context(entry.trace_id)
            if context_record is not None:
                fragments = dict(context_record.fragments)

        def fragment(cls: type[_ModelT], key: str) -> _ModelT | None:
            raw = fragments.get(key)
            return cls.model_validate(raw) if raw is not None else None

        proposal = fragment(TradeProposal, "proposal")
        decision = fragment(RiskDecision, "risk_decision")
        instrument = rt.instruments.get(outcome.instrument_id)
        contract_size = getattr(instrument, "contract_size", Decimal("100000"))
        path = rt.ledger.price_path(outcome.position_id) if outcome.position_id else ()
        return AnalysisContext(
            outcome=outcome,
            strategy_id=entry.strategy_id if entry is not None else rt.config.strategy_id,
            strategy_version=(
                entry.strategy_version if entry is not None else rt.config.strategy_version
            ),
            entry_stop=(
                entry.stop_loss
                if entry is not None
                else proposal.stop_loss
                if proposal is not None
                else None
            ),
            entry_take=(
                entry.take_profit
                if entry is not None
                else proposal.take_profit
                if proposal is not None
                else None
            ),
            risk_decision=decision,
            quant=fragment(QuantSignal, "quant"),
            llm=fragment(LLMSignal, "llm"),
            fused=fragment(FusedSignal, "fused"),
            memory=fragment(MemoryContext, "memory"),
            price_path=path,
            regime=outcome.regime_at_entry,
            contract_size=contract_size,
        )

    @staticmethod
    def _quant_evaluation(result: AnalysisResult) -> QuantEvaluation:
        quant_quality = next(
            (quality for quality in result.signal_quality if quality.producer == "quant"), None
        )
        return QuantEvaluation(
            direction_correct=(
                quant_quality.direction_correct
                if quant_quality is not None and quant_quality.present
                else None
            ),
            calibration_error=(
                quant_quality.brier_error
                if quant_quality is not None and quant_quality.present
                else None
            ),
            signal_accuracy=None,
        )

    def _write_artifact(
        self,
        rt: StageRuntime,
        record: PostTradeReviewRecord,
        outcome: TradeOutcome,
        review_id: UUID,
    ) -> str | None:
        artifact_store = rt.extras.get("artifact_store")
        if artifact_store is None or not getattr(rt.config.posttrade, "store_artifacts", True):
            return None
        key = artifact_key(outcome.closed_at, review_id)
        path_json = [
            point.model_dump(mode="json")
            for point in rt.ledger.price_path(outcome.position_id or "")
        ]
        try:
            artifact_store.put_json(
                key, build_artifact(record, self._fragments_json(rt, outcome), path_json)
            )
            return key
        except Exception as exc:  # artifact outage never breaks the audit trail
            rt.audit.record(
                "posttrade.artifact.failed",
                target=str(outcome.trade_id),
                trace_id=record.trace_id,
                outcome="ERROR",
                metadata={"error": type(exc).__name__},
            )
            return None

    def _write_vault_note(
        self,
        rt: StageRuntime,
        record: PostTradeReviewRecord,
        outcome: TradeOutcome,
        review_id: UUID,
    ) -> str | None:
        vault_writer = rt.extras.get("vault_writer")
        if vault_writer is None or not getattr(rt.config.posttrade, "write_vault_notes", True):
            return None
        path = note_path(outcome.closed_at, outcome.instrument_id, review_id)
        try:
            from adapters.obsidian import ensure_secret_free

            content = render_note(record)
            ensure_secret_free(record.review_payload, content)
            vault_writer.write_note(path, content)
            return path
        except Exception as exc:
            rt.audit.record(
                "posttrade.vault_note.failed",
                target=str(outcome.trade_id),
                trace_id=record.trace_id,
                outcome="ERROR",
                metadata={"error": type(exc).__name__},
            )
            return None

    def _ingest_lesson(
        self,
        rt: StageRuntime,
        outcome: TradeOutcome,
        result: AnalysisResult,
        review_id: UUID,
        strategy_id: str,
        trace_id: UUID,
        now: datetime,
    ) -> MemoryEpisode | None:
        memory = rt.extras.get("memory")
        if memory is None or not getattr(rt.config.posttrade, "ingest_lessons", True):
            return None
        metrics = result.metrics
        episode = MemoryEpisode(
            episode_id=uuid5(_REVIEW_NS, f"episode:{review_id}"),
            layer=MemoryLayer.LONG_TERM,
            valid_from=now,
            summary=(
                f"Postmortem {outcome.instrument_id} {outcome.direction.value}: "
                f"verdict {result.verdict}, net {metrics.pnl_net}, "
                f"{f'{metrics.r_multiple:.2f}R' if metrics.r_multiple is not None else 'R unknown'}"
            ),
            entities=[
                EntityRef(
                    entity_id=f"instrument:{outcome.instrument_id}",
                    entity_type="Instrument",
                    name=outcome.instrument_id,
                ),
                EntityRef(
                    entity_id=f"strategy:{strategy_id}",
                    entity_type="Strategy",
                    name=strategy_id,
                ),
                EntityRef(
                    entity_id=f"trade:{outcome.trade_id}",
                    entity_type="Trade",
                    name=str(outcome.trade_id),
                ),
            ],
            relations=[
                RelationRef(
                    source=f"trade:{outcome.trade_id}",
                    relation="GENERATED_BY",
                    target=f"strategy:{strategy_id}",
                )
            ],
            importance=0.7,
            source_trace_id=trace_id,
            content={
                "lesson_type": "postmortem",
                "review_id": str(review_id),
                "instrument_id": outcome.instrument_id,
                "direction": outcome.direction.value,
                "verdict": result.verdict,
                "market_regime": metrics.market_regime,
                "pnl_net": str(metrics.pnl_net),
                "r_multiple": metrics.r_multiple,
                "alpha_pct": metrics.alpha_pct,
                "mae_pct": metrics.mae_pct,
                "mfe_pct": metrics.mfe_pct,
                "exit_reason": outcome.exit_reason,
                "expected_vs_actual": result.expected_vs_actual,
                "lessons": result.lessons,
                "signal_quality": [
                    quality.model_dump(mode="json") for quality in result.signal_quality
                ],
            },
            trace_id=trace_id,
            produced_at=now,
            provenance=rt.provenance(_PRODUCER, now),
        )
        try:
            memory.ingest(
                episode,
                source=_PRODUCER,
                event_time=outcome.closed_at,
                available_time=now,
                ingested_at=now,
            )
            return episode
        except Exception as exc:  # memory outage never breaks the audit trail
            rt.audit.record(
                "memory.ingest.failed",
                target=outcome.instrument_id,
                trace_id=trace_id,
                outcome="ERROR",
                metadata={"error": type(exc).__name__},
            )
            return None

    def _fragments_json(self, rt: StageRuntime, outcome: TradeOutcome) -> dict[str, dict[str, Any]]:
        """The captured decision context, for embedding in the artifact."""
        entry = self._entry_lifecycle(rt, outcome)
        if entry is None:
            return {}
        context_record = rt.store.get_context(entry.trace_id)
        if context_record is None:
            return {}
        return {key: dict(value) for key, value in context_record.fragments.items()}
