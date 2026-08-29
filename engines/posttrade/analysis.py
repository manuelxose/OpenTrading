"""Post-trade analysis engine (architecture §17).

Turns one closed-and-reconciled trade plus its captured decision context into
a structured postmortem:

- canonical :class:`TradeMetrics` (see :mod:`engines.posttrade.metrics`);
- an *independent* quality evaluation per chain link — QuantSignal, LLMSignal,
  FusedSignal, RiskDecision, execution — each judged against the realized
  outcome, never against another link's self-assessment;
- the expected-vs-actual comparison (the memory learns from the gap);
- deterministic lessons, thesis verdict and summary.

Strictly read-only over risk state: the engine consumes the
:class:`RiskDecision` payload that was produced at entry and never imports or
touches risk-limit writers (INV-1, INV-4).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.domain.enums import RiskDecisionType, SignalDirection
from core.schemas import (
    FusedSignal,
    LLMSignal,
    MemoryContext,
    QuantSignal,
    RiskDecision,
    TradeOutcome,
)
from core.schemas.posttrade import (
    ExecutionQualityRecord,
    RiskQualityRecord,
    SignalQualityRecord,
    TradeMetrics,
)

from engines.posttrade.metrics import (
    MetricsInput,
    PricePoint,
    brier_error,
    compute_trade_metrics,
    direction_correct,
    signed_return_pct,
)

__all__ = [
    "AnalysisContext",
    "AnalysisResult",
    "PostTradeAnalyzer",
    "analyze",
]

#: Producers evaluated independently, in canonical order (INV-16 input order).
PRODUCER_ORDER = ("quant", "llm", "fused", "memory")

#: A stop is considered breached when the realized adverse excursion exceeded
#: the planned stop distance by more than this relative tolerance.
_STOP_BREACH_TOLERANCE = Decimal("1.05")

#: Fees above this share of the gross move are flagged as erosion.
_FEE_EROSION_SHARE = 0.2

#: A stop-loss exit reason keyword match marks a defensive exit.
_STOP_EXIT_KEYWORDS = ("stop", "sl")


@dataclass(frozen=True)
class AnalysisContext:
    """Everything the analyzer reads for one closed trade (pure inputs)."""

    outcome: TradeOutcome
    strategy_id: str
    strategy_version: str
    entry_stop: Decimal | None = None
    entry_take: Decimal | None = None
    risk_decision: RiskDecision | None = None
    quant: QuantSignal | None = None
    llm: LLMSignal | None = None
    fused: FusedSignal | None = None
    memory: MemoryContext | None = None
    price_path: tuple[PricePoint, ...] = ()
    regime: str | None = None
    benchmark_return_pct: float | None = None
    contract_size: Decimal = Decimal("100000")
    venue: str = "paper"


@dataclass(frozen=True)
class AnalysisResult:
    """The full postmortem payload produced by :func:`analyze`."""

    metrics: TradeMetrics
    signal_quality: list[SignalQualityRecord]
    risk_quality: RiskQualityRecord
    execution_quality: ExecutionQualityRecord
    expected_vs_actual: dict[str, float]
    lessons: list[str]
    verdict: str
    verdict_confidence: float
    thesis_summary: str


class PostTradeAnalyzer:
    """Deterministic analysis engine (no IO, no risk-limit writes)."""

    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        return analyze(context)


def _signals(context: AnalysisContext) -> tuple[tuple[str, Any], ...]:
    """The captured producer stances, in canonical order."""
    mapping = {
        "quant": context.quant,
        "llm": context.llm,
        "fused": context.fused,
        "memory": context.memory,
    }
    return tuple((name, mapping[name]) for name in PRODUCER_ORDER)


def analyze(context: AnalysisContext) -> AnalysisResult:
    outcome = context.outcome
    entry = outcome.entry_price
    exit_price = outcome.exit_price
    realized_up = exit_price >= entry

    # ── independent signal evaluations (INV-16) ────────────────────────────────
    calibration: dict[str, float] = {}
    signal_quality: list[SignalQualityRecord] = []
    for producer, signal in _signals(context):
        direction: SignalDirection | None = None
        confidence: float | None = None
        notes: list[str] = []
        if signal is None:
            signal_quality.append(
                SignalQualityRecord(
                    producer=producer,
                    present=False,
                    notes=["not captured at entry — excluded from evaluation"],
                )
            )
            continue
        direction = signal.direction
        confidence = signal.confidence
        correct = direction_correct(direction, realized_up)
        error = brier_error(confidence, correct) if correct is not None else None
        if error is not None:
            calibration[producer] = error
        if producer == "fused" and signal.missing_inputs:
            notes.append(f"fused without inputs: {', '.join(signal.missing_inputs)}")
        if producer == "fused" and signal.disagreements:
            notes.append(f"{len(signal.disagreements)} disagreement(s) resolved by policy")
        signal_quality.append(
            SignalQualityRecord(
                producer=producer,
                present=True,
                direction=direction,
                confidence=confidence,
                direction_correct=correct,
                brier_error=error,
                notes=notes,
            )
        )

    # ── predicted move: quant's expected return when present, else the plan ────
    expected_return_pct: float | None = None
    if context.quant is not None and context.quant.expected_return is not None:
        sign = 1.0 if context.quant.direction is SignalDirection.LONG else -1.0
        expected_return_pct = sign * float(context.quant.expected_return) * 100
    elif context.entry_take is not None:
        expected_return_pct = signed_return_pct(entry, context.entry_take, outcome.direction)

    metrics = compute_trade_metrics(
        MetricsInput(
            outcome=outcome,
            risk_amount=context.risk_decision.risk_amount if context.risk_decision else None,
            expected_return_pct=expected_return_pct,
            benchmark_return_pct=context.benchmark_return_pct,
            path=context.price_path,
            regime=context.regime,
            signal_calibration_error=calibration,
            planned_stop=context.entry_stop,
            planned_take=context.entry_take,
        )
    )

    # ── Risk Decision quality (read-only; limits are never re-sized) ───────────
    risk_quality = _evaluate_risk(context, metrics)
    execution_quality = _evaluate_execution(context, metrics)

    # ── expected vs actual (the memory learns from this gap) ───────────────────
    actual_r = metrics.r_multiple if metrics.r_multiple is not None else 0.0
    expected_vs_actual: dict[str, float] = {
        "direction_hit": 1.0 if direction_correct(outcome.direction, realized_up) else 0.0,
        "actual_r": actual_r,
        "actual_return_pct": metrics.actual_return_pct if metrics.actual_return_pct else 0.0,
    }
    if metrics.expected_return_pct is not None:
        expected_vs_actual["expected_return_pct"] = metrics.expected_return_pct
    if metrics.expected_r is not None:
        expected_vs_actual["expected_r"] = metrics.expected_r
    if metrics.prediction_error_pct is not None:
        expected_vs_actual["prediction_error_pct"] = metrics.prediction_error_pct

    # ── verdict, lessons, summary ───────────────────────────────────────────────
    verdict, verdict_confidence = _verdict(context, metrics, realized_up)
    lessons = _lessons(context, metrics, signal_quality, risk_quality, execution_quality)
    thesis_summary = _thesis_summary(context, metrics, verdict)

    return AnalysisResult(
        metrics=metrics,
        signal_quality=signal_quality,
        risk_quality=risk_quality,
        execution_quality=execution_quality,
        expected_vs_actual=expected_vs_actual,
        lessons=lessons,
        verdict=verdict,
        verdict_confidence=verdict_confidence,
        thesis_summary=thesis_summary,
    )


def _evaluate_risk(context: AnalysisContext, metrics: TradeMetrics) -> RiskQualityRecord:
    decision = context.risk_decision
    notes: list[str] = []
    if decision is None:
        return RiskQualityRecord(
            limits_respected=False,
            notes=["no RiskDecision captured in the trade context — cannot attest limits"],
        )
    approved = decision.decision in (RiskDecisionType.APPROVE, RiskDecisionType.RESIZE)
    limits_respected = approved

    size_respected: bool | None = None
    if approved and decision.approved_quantity is not None and context.contract_size > 0:
        approved_units = decision.approved_quantity * context.contract_size
        tolerance = max(approved_units, context.outcome.quantity) * Decimal("1e-6")
        size_respected = abs(approved_units - context.outcome.quantity) <= tolerance
        if not size_respected:
            notes.append(
                f"filled size deviates from approved size "
                f"(approved={approved_units}, filled={context.outcome.quantity})"
            )

    planned_stop_respected: bool | None = None
    if context.entry_stop is not None and metrics.mae_pct is not None:
        entry = context.outcome.entry_price
        stop_distance = abs(context.entry_stop - entry)
        mae_price = entry * Decimal(str(metrics.mae_pct)) / 100
        planned_stop_respected = mae_price <= stop_distance * _STOP_BREACH_TOLERANCE
        if not planned_stop_respected:
            notes.append("adverse excursion exceeded the planned stop distance")
    if approved and decision.reason_codes:
        notes.append(
            "resized by the Risk Engine: " + ", ".join(c.value for c in decision.reason_codes)
        )
    if not approved and decision.reason_codes:
        notes.append("rejected at entry: " + ", ".join(c.value for c in decision.reason_codes))
    if approved:
        notes.append(f"risk amount approved: {decision.risk_amount}")
    return RiskQualityRecord(
        limits_respected=limits_respected,
        decision=decision.decision,
        approved=approved,
        size_respected=size_respected,
        planned_stop_respected=planned_stop_respected,
        risk_amount=decision.risk_amount,
        notes=notes,
    )


def _evaluate_execution(context: AnalysisContext, metrics: TradeMetrics) -> ExecutionQualityRecord:
    entry = context.outcome.entry_price
    quantity = context.outcome.quantity
    notional = entry * quantity
    notes: list[str] = []
    slippage_pct: float | None = None
    fees_pct: float | None = None
    if notional > 0:
        slippage_pct = float(metrics.slippage / notional * 100)
        fees_pct = float(metrics.fees / notional * 100)
    fill_quality = "paper"
    if context.venue != "paper":
        fill_quality = "venue-fill"
    if metrics.slippage > 0:
        notes.append(f"slippage {metrics.slippage} accounted in the outcome")
    if metrics.fees > 0:
        notes.append(f"fees {metrics.fees} accounted in the outcome")
    return ExecutionQualityRecord(
        slippage_pct=slippage_pct,
        fees_pct=fees_pct,
        latency_ms=None,
        fill_quality=fill_quality,
        notes=notes,
    )


def _verdict(
    context: AnalysisContext, metrics: TradeMetrics, realized_up: bool
) -> tuple[str, float]:
    direction_right = direction_correct(context.outcome.direction, realized_up) is True
    confidence = 0.5
    if context.fused is not None:
        confidence = context.fused.confidence
    elif context.quant is not None:
        confidence = context.quant.confidence
    if direction_right and metrics.pnl_net > 0:
        return "SUPPORTED", confidence
    if not direction_right and metrics.pnl_net < 0:
        return "CONTRADICTED", confidence
    return "INCONCLUSIVE", confidence


def _lessons(
    context: AnalysisContext,
    metrics: TradeMetrics,
    signal_quality: list[SignalQualityRecord],
    risk_quality: RiskQualityRecord,
    execution_quality: ExecutionQualityRecord,
) -> list[str]:
    lessons: list[str] = []
    regime = metrics.market_regime
    instrument = context.outcome.instrument_id

    for quality in signal_quality:
        if quality.present and quality.direction_correct is False:
            confidence = f"{quality.confidence:.2f}" if quality.confidence is not None else "n/a"
            lessons.append(
                f"{instrument}: {quality.producer} direction was wrong "
                f"(confidence={confidence}) — review its weight in regime {regime}"
            )

    if metrics.r_multiple is not None:
        if metrics.r_multiple <= -1:
            lessons.append(f"{instrument}: lost {metrics.r_multiple:.2f}R — stop distance review")
        elif metrics.r_multiple >= 1:
            lessons.append(f"{instrument}: winner at {metrics.r_multiple:.2f}R")

    if metrics.exit_efficiency is not None and metrics.exit_efficiency < 0.5:
        lessons.append(
            f"{instrument}: gave back more than half of the favorable excursion "
            f"(exit efficiency {metrics.exit_efficiency:.2f}) — consider a trailing exit"
        )
    if (
        metrics.entry_efficiency is not None
        and metrics.entry_efficiency < 0
        and (metrics.mfe_pct or 0.0) > 0
    ):
        lessons.append(f"{instrument}: closed below entry despite favorable excursion")

    if (
        execution_quality.fees_pct is not None
        and metrics.actual_return_pct is not None
        and metrics.actual_return_pct != 0
        and execution_quality.fees_pct / abs(metrics.actual_return_pct) > _FEE_EROSION_SHARE
    ):
        lessons.append(f"{instrument}: fees consumed more than 20% of the gross move")

    if (
        metrics.alpha_pct is not None
        and metrics.expected_return_pct is not None
        and abs(metrics.expected_return_pct) > 0
        and abs(metrics.alpha_pct) > 0.5 * abs(metrics.expected_return_pct)
    ):
        lessons.append(
            f"{instrument}: outcome deviated strongly from the plan "
            f"(expected {metrics.expected_return_pct:.3f}%, "
            f"actual {metrics.actual_return_pct:.3f}%)"
        )

    quant = next((q for q in signal_quality if q.producer == "quant"), None)
    llm = next((q for q in signal_quality if q.producer == "llm"), None)
    if (
        quant is not None
        and llm is not None
        and quant.present
        and llm.present
        and quant.direction is not None
        and llm.direction is not None
        and quant.direction != llm.direction
    ):
        winner = "quant" if quant.direction_correct else "llm"
        lessons.append(f"{instrument}: quant and llm disagreed in {regime}; {winner} was correct")

    if any(keyword in context.outcome.exit_reason.lower() for keyword in _STOP_EXIT_KEYWORDS):
        lessons.append(f"{instrument}: stop-loss exit recorded ({context.outcome.exit_reason})")
    if risk_quality.planned_stop_respected is False:
        lessons.append(f"{instrument}: stop breach — exit slipped beyond the planned stop")

    return lessons[:10]


def _thesis_summary(context: AnalysisContext, metrics: TradeMetrics, verdict: str) -> str:
    direction = context.outcome.direction.value
    r_text = f"{metrics.r_multiple:.2f}R" if metrics.r_multiple is not None else "R unknown"
    return (
        f"{context.outcome.instrument_id} {direction} closed {r_text} "
        f"({metrics.pnl_net} net) — verdict {verdict}"
    )
