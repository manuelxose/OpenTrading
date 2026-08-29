"""Translation layer: canonical domain contracts ↔ upstream TradingAgents.

In:  ``ResearchRequest`` (+ optional ``MarketSnapshot``)  →  ``UpstreamInput``
Out: normalized upstream state  →  canonical ``LLMSignal``

Everything here is pure and deterministic — no upstream imports, no LLM calls,
no I/O beyond reading the prompt template once. This is what lets the mock
adapter and the live adapter share exactly one mapping path (contract tests
depend on that).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from core.domain.enums import SignalDirection
from core.schemas.base import Provenance, ensure_utc
from core.schemas.market import MarketSnapshot
from core.schemas.research import EvidenceRef, ResearchRequest
from core.schemas.signals import CommitteeMember, LLMSignal

from adapters.tradingagents.errors import TradingAgentsMappingError
from adapters.tradingagents.pin import UPSTREAM_COMMIT
from adapters.tradingagents.schemas import (
    AssetType,
    ModelMetadata,
    TokenUsage,
    TradingAgentsRating,
    UpstreamInput,
    UpstreamRunResult,
)

__all__ = [
    "PRODUCER",
    "PROMPT_VERSION",
    "RATING_PROFILE",
    "infer_stance",
    "parse_rating",
    "parse_trader_action",
    "request_to_upstream_input",
    "resolve_as_of",
    "resolve_instrument_id",
    "result_to_signal",
    "state_to_result",
]

#: Producer tag recorded in signal provenance.
PRODUCER = "adapters.tradingagents"

#: Prompt/config version recorded on every signal (auditable rollbacks).
PROMPT_VERSION = "tradingagents-adapter-1.0.0"

#: Advisory 5-tier profile (see prompts/rating_scale.md). NOT calibrated fusion
#: weights (INV-16); NEVER executable sizing (INV-1).
RATING_PROFILE: dict[TradingAgentsRating, tuple[SignalDirection, float, float]] = {
    TradingAgentsRating.BUY: (SignalDirection.LONG, 0.90, 0.80),
    TradingAgentsRating.OVERWEIGHT: (SignalDirection.LONG, 0.70, 0.70),
    TradingAgentsRating.HOLD: (SignalDirection.FLAT, 0.50, 0.50),
    TradingAgentsRating.UNDERWEIGHT: (SignalDirection.SHORT, 0.70, 0.70),
    TradingAgentsRating.SELL: (SignalDirection.SHORT, 0.90, 0.80),
}

#: Ordering of analyst evidence inside the committee.
_ANALYST_SLOTS: tuple[tuple[str, str], ...] = (
    ("Fundamentals Analyst", "fundamentals_report"),
    ("Market Analyst", "market_report"),
    ("Sentiment Analyst", "sentiment_report"),
    ("News Analyst", "news_report"),
)

_RATING_RE = re.compile(r"\*\*Rating\*\*:\s*([A-Za-z]+)", re.IGNORECASE)
_RATING_PLAIN_RE = re.compile(r"\bRating:\s*([A-Za-z]+)", re.IGNORECASE)
_TRADER_FINAL_RE = re.compile(
    r"FINAL TRANSACTION PROPOSAL:\s*\*{0,2}\s*(BUY|SELL|HOLD)\*{0,2}", re.IGNORECASE
)
_TRADER_ACTION_RE = re.compile(r"\*\*Action\*\*:\s*([A-Za-z]+)", re.IGNORECASE)

_BULLISH_WORDS = frozenset(
    {
        "bullish",
        "overweight",
        "upside",
        "growth",
        "strong",
        "beat",
        "buy",
        "long",
        "momentum",
        "positive",
        "rally",
        "outperform",
        "attractive",
        "expand",
        "improve",
        "favorable",
        "surge",
        "recovery",
        "upgrade",
    }
)
_BEARISH_WORDS = frozenset(
    {
        "bearish",
        "underweight",
        "downside",
        "decline",
        "weak",
        "miss",
        "sell",
        "short",
        "resistance",
        "negative",
        "risk",
        "pullback",
        "underperform",
        "recession",
        "deteriorate",
        "unfavorable",
        "cut",
        "slowdown",
        "downgrade",
        "overvalued",
        "loss",
    }
)

_CONTEXT_TEMPLATE_PATH = Path(__file__).resolve().parent / "prompts" / "context.md"
_CONTEXT_TEMPLATE: Template | None = None


def _context_template() -> Template:
    global _CONTEXT_TEMPLATE
    if _CONTEXT_TEMPLATE is None:
        _CONTEXT_TEMPLATE = Template(_CONTEXT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return _CONTEXT_TEMPLATE


def resolve_as_of(request: ResearchRequest, snapshot: MarketSnapshot | None) -> datetime:
    """Resolve the explicit ``as_of`` anchor (requirement: explicit as_of context).

    Precedence: the snapshot's ``as_of`` is authoritative. A conflicting
    ``context["as_of"]`` is a mapping error; a missing one when no snapshot is
    given is a mapping error. INV-3 defense in depth: the snapshot timestamp
    must never be posterior to ``as_of`` (the schema already enforces this).
    """
    snapshot_as_of: datetime | None = None
    if snapshot is not None:
        snapshot_as_of = ensure_utc(snapshot.as_of)
        if ensure_utc(snapshot.source_timestamp) > snapshot_as_of:
            raise TradingAgentsMappingError(
                f"snapshot source_timestamp {snapshot.source_timestamp.isoformat()} "
                f"is posterior to as_of {snapshot_as_of.isoformat()} (INV-3)"
            )

    raw = request.context.get("as_of")
    context_as_of: datetime | None = None
    if raw is not None:
        context_as_of = _coerce_datetime(raw, label="ResearchRequest.context['as_of']")

    if snapshot_as_of is not None:
        if context_as_of is not None and context_as_of != snapshot_as_of:
            raise TradingAgentsMappingError(
                "context['as_of'] conflicts with the MarketSnapshot as_of"
            )
        return snapshot_as_of
    if context_as_of is None:
        raise TradingAgentsMappingError(
            "explicit as_of context is required: pass a MarketSnapshot or set "
            "ResearchRequest.context['as_of']"
        )
    return context_as_of


def _coerce_datetime(raw: Any, *, label: str) -> datetime:
    if isinstance(raw, datetime):
        return ensure_utc(raw)
    if isinstance(raw, str):
        try:
            return ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError as exc:
            raise TradingAgentsMappingError(f"{label} is not a valid timestamp: {raw!r}") from exc
    raise TradingAgentsMappingError(f"{label} must be a datetime or ISO-8601 string, got {raw!r}")


def resolve_instrument_id(request: ResearchRequest, snapshot: MarketSnapshot | None) -> str:
    """Resolve the canonical instrument id (from the snapshot, else context)."""
    snapshot_id = snapshot.instrument_id if snapshot is not None else None
    context_id = request.context.get("instrument_id")
    if snapshot_id is not None and context_id and context_id != snapshot_id:
        raise TradingAgentsMappingError(
            f"context['instrument_id']={context_id!r} conflicts with snapshot "
            f"instrument_id={snapshot_id!r}"
        )
    instrument_id = snapshot_id or context_id
    if not instrument_id or not isinstance(instrument_id, str):
        raise TradingAgentsMappingError(
            "instrument id is required: pass a MarketSnapshot or set "
            "ResearchRequest.context['instrument_id']"
        )
    return instrument_id


def _validate_point_in_time_evidence(request: ResearchRequest, as_of: datetime) -> None:
    """Reject injected context evidence that is not provably valid at ``as_of``.

    The domain must only inject point-in-time valid data (INV-3); the adapter
    re-checks it at the boundary so a bypass fails loudly instead of silently.
    """
    evidence = request.context.get("evidence", [])
    if not evidence:
        return
    if not isinstance(evidence, list):
        raise TradingAgentsMappingError("context['evidence'] must be a list")
    for entry in evidence:
        if not isinstance(entry, dict) or "valid_at" not in entry:
            raise TradingAgentsMappingError(
                "every context['evidence'] entry must carry a 'valid_at' timestamp"
            )
        valid_at = _coerce_datetime(entry["valid_at"], label="context['evidence'].valid_at")
        if valid_at > as_of:
            raise TradingAgentsMappingError(
                f"context evidence has valid_at {valid_at.isoformat()} posterior to "
                f"as_of {as_of.isoformat()} (INV-3)"
            )


def request_to_upstream_input(
    request: ResearchRequest, snapshot: MarketSnapshot | None
) -> UpstreamInput:
    """Translate a canonical request into the upstream ``propagate`` surface."""
    as_of = resolve_as_of(request, snapshot)
    instrument_id = resolve_instrument_id(request, snapshot)
    _validate_point_in_time_evidence(request, as_of)

    asset_type_raw = request.context.get("asset_type", "stock")
    if asset_type_raw not in ("stock", "crypto"):
        raise TradingAgentsMappingError(
            f"context['asset_type'] must be 'stock' or 'crypto', got {asset_type_raw!r}"
        )
    asset_type: AssetType = asset_type_raw

    return UpstreamInput(
        ticker=instrument_id,
        trade_date=as_of.strftime("%Y-%m-%d"),
        asset_type=asset_type,
        as_of=as_of,
        context_payload=_render_context_payload(request, snapshot),
    )


def _render_context_payload(
    request: ResearchRequest, snapshot: MarketSnapshot | None
) -> dict[str, Any]:
    """Render the point-in-time context block (prompts/context.md) for the run."""
    hypotheses_block = "\n".join(f"- {h}" for h in request.hypotheses) or "- (none)"
    scope_block = "\n".join(f"- {s}" for s in request.scope) or "- (none)"

    if snapshot is not None:
        snapshot_block = (
            f"- source: {snapshot.source} (source_timestamp: "
            f"{snapshot.source_timestamp.isoformat()})\n"
            f"- bid: {snapshot.bid} / ask: {snapshot.ask}"
            + (f" (last: {snapshot.last})" if snapshot.last is not None else "")
            + (f"\n- timeframe: {snapshot.timeframe.value}" if snapshot.timeframe else "")
        )
    else:
        snapshot_block = "- (no snapshot provided)"

    known = ("portfolio_context", "memory_context", "regime_context")
    extra = {key: request.context[key] for key in known if request.context.get(key)}
    extra_block = json.dumps(extra, default=str, sort_keys=True) if extra else "- (none)"

    if snapshot is not None:
        instrument_id = snapshot.instrument_id
        as_of_text = snapshot.as_of.isoformat()
    else:
        instrument_id = str(request.context.get("instrument_id", ""))
        as_of_text = str(request.context.get("as_of", ""))

    rendered = _context_template().safe_substitute(
        instrument_id=instrument_id,
        as_of=as_of_text,
        question=request.question,
        hypotheses_block=hypotheses_block,
        snapshot_block=snapshot_block,
        scope_block=scope_block,
        extra_block=extra_block,
    )
    return {
        "instrument_id": instrument_id,
        "question": request.question,
        "rendered": rendered,
    }


def parse_rating(text: str) -> TradingAgentsRating:
    """Deterministically read the 5-tier rating out of upstream markdown/prose.

    Covers the upstream render guarantee (``**Rating**: Buy``), the legacy
    ``Rating: Buy`` shape, and the bare tier string returned by upstream's
    SignalProcessor. No LLM call, no lenient guessing: an unknown tier is a
    mapping error (fail safely).
    """
    for regex in (_RATING_RE, _RATING_PLAIN_RE):
        match = regex.search(text)
        if match:
            raw = match.group(1).strip()
            return _tier(raw)
    bare = text.strip()
    if len(bare) <= 32 and " " not in bare and ":" not in bare and "*" not in bare:
        return _tier(bare)
    raise TradingAgentsMappingError(f"no parseable rating in upstream output: {text[:120]!r}")


def _tier(raw: str) -> TradingAgentsRating:
    lowered = raw.lower()
    for tier in TradingAgentsRating:
        if lowered == tier.value.lower():
            return tier
    raise TradingAgentsMappingError(f"unknown upstream rating tier: {raw!r}")


_ACTION_TO_DIRECTION = {
    "BUY": SignalDirection.LONG,
    "SELL": SignalDirection.SHORT,
    "HOLD": SignalDirection.FLAT,
}


def parse_trader_action(text: str) -> SignalDirection | None:
    """Read the Trader's BUY/HOLD/SELL action out of its rendered proposal."""
    match = _TRADER_FINAL_RE.search(text) or _TRADER_ACTION_RE.search(text)
    if match is None:
        return None
    return _ACTION_TO_DIRECTION.get(match.group(1).upper())


def infer_stance(text: str, *, default: SignalDirection) -> SignalDirection:
    """Deterministic, documented heuristic: net bullish/bearish token weight.

    Used only to label committee members whose upstream output has no explicit
    direction field (analyst reports). Ambiguous text falls back to ``default``.
    """
    words = re.findall(r"[a-z]+", text.lower())
    score = sum(1 for w in words if w in _BULLISH_WORDS) - sum(
        1 for w in words if w in _BEARISH_WORDS
    )
    if score > 0:
        return SignalDirection.LONG
    if score < 0:
        return SignalDirection.SHORT
    return default


def state_to_result(
    state: dict[str, Any],
    *,
    ticker: str,
    as_of: datetime,
    rating: TradingAgentsRating,
    latency_ms: int,
    model_metadata: ModelMetadata,
    token_usage: TokenUsage | None,
    cost_usd: float | None,
    trace_id: UUID | None = None,
) -> UpstreamRunResult:
    """Normalize the upstream final state dict into an adapter-internal result.

    Evidence is preserved verbatim per committee role: the four analyst
    reports, the bull/bear researcher histories, the Trader proposal and the
    Portfolio Manager decision (plus the risk debate history).
    """
    debate = state.get("investment_debate_state") or {}
    risk = state.get("risk_debate_state") or {}
    analyst_reports = {key: str(state.get(key, "") or "") for _, key in _ANALYST_SLOTS}
    trade_date = str(state.get("trade_date") or as_of.strftime("%Y-%m-%d"))
    return UpstreamRunResult(
        ticker=ticker,
        trade_date=trade_date,
        as_of=ensure_utc(as_of),
        rating=rating,
        decision_markdown=str(state.get("final_trade_decision") or ""),
        investment_plan=str(state.get("investment_plan") or ""),
        trader_plan=str(state.get("trader_investment_plan") or ""),
        analyst_reports=analyst_reports,
        bull_history=str(debate.get("bull_history") or ""),
        bear_history=str(debate.get("bear_history") or ""),
        risk_history=str(risk.get("history") or ""),
        model_metadata=model_metadata,
        token_usage=token_usage,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        trace_id=trace_id,
    )


def build_committee(result: UpstreamRunResult) -> list[CommitteeMember]:
    """Preserve analyst / researcher / trader / portfolio-manager evidence.

    The Portfolio Manager member is always present (its decision is the signal
    source), so the ``min_length=1`` schema constraint holds by construction.
    """
    pm_direction, _, _ = RATING_PROFILE[result.rating]
    members: list[CommitteeMember] = []

    for name, key in _ANALYST_SLOTS:
        report = result.analyst_reports.get(key, "").strip()
        if report:
            members.append(
                CommitteeMember(
                    name=name,
                    role="analyst",
                    stance=infer_stance(report, default=SignalDirection.FLAT),
                    argument=report,
                )
            )

    if result.bull_history.strip():
        members.append(
            CommitteeMember(
                name="Bull Researcher",
                role="researcher",
                stance=SignalDirection.LONG,
                argument=result.bull_history,
            )
        )
    if result.bear_history.strip():
        members.append(
            CommitteeMember(
                name="Bear Researcher",
                role="researcher",
                stance=SignalDirection.SHORT,
                argument=result.bear_history,
            )
        )

    if result.trader_plan.strip():
        trader_stance = parse_trader_action(result.trader_plan) or infer_stance(
            result.trader_plan, default=pm_direction
        )
        members.append(
            CommitteeMember(
                name="Trader",
                role="trader",
                stance=trader_stance,
                argument=result.trader_plan,
            )
        )

    members.append(
        CommitteeMember(
            name="Portfolio Manager",
            role="portfolio_manager",
            stance=pm_direction,
            argument=result.decision_markdown,
        )
    )
    return members


def result_to_signal(
    result: UpstreamRunResult,
    *,
    request: ResearchRequest,
    snapshot: MarketSnapshot | None = None,
    trace_id: UUID | None = None,
    produced_at: datetime,
) -> LLMSignal:
    """Translate a normalized upstream result into the canonical ``LLMSignal``.

    Advisory only: direction/strength/confidence come from the documented
    rating profile; upstream sizing/stop prose stays inside the Trader member's
    argument text and never becomes an executable value (INV-1/INV-2).
    """
    direction, strength, confidence = RATING_PROFILE[result.rating]
    meta = result.model_metadata

    signal_id = uuid5(
        NAMESPACE_URL,
        f"{request.request_id}:{result.as_of.isoformat()}:{meta.provider}:"
        f"{meta.deep_think_llm}:{meta.quick_think_llm}",
    )
    evidence: list[EvidenceRef] = [
        EvidenceRef(
            ref_id=f"tradingagents-run:{request.request_id}",
            kind="artifact",
            source=f"TauricResearch/TradingAgents@{meta.upstream_version}",
            valid_at=result.as_of,
            summary=f"Upstream committee run ({result.rating.value}), {result.latency_ms} ms",
        ),
        EvidenceRef(
            ref_id=f"research-request:{request.request_id}",
            kind="document",
            source="OpenTrading.ResearchRequest",
            valid_at=result.as_of,
            summary=request.title,
        ),
    ]
    if snapshot is not None:
        evidence.append(
            EvidenceRef(
                ref_id=(
                    f"market-snapshot:{snapshot.source}:{snapshot.instrument_id}:"
                    f"{snapshot.source_timestamp.isoformat()}"
                ),
                kind="dataset",
                source=snapshot.source,
                valid_at=snapshot.source_timestamp,
                summary="Point-in-time market snapshot injected as context",
            )
        )

    return LLMSignal(
        signal_id=signal_id,
        instrument_id=result.ticker,
        direction=direction,
        strength=strength,
        confidence=confidence,
        reasoning=result.decision_markdown,
        committee=build_committee(result),
        evidence_refs=evidence,
        model_name=meta.deep_think_llm,
        provider=meta.provider,
        prompt_version=meta.prompt_version,
        as_of=result.as_of,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        trace_id=trace_id,
        produced_at=ensure_utc(produced_at),
        provenance=Provenance(
            producer=PRODUCER,
            produced_at=ensure_utc(produced_at),
            source_ids={
                "request_id": str(request.request_id),
                "upstream_version": meta.upstream_version,
                "upstream_commit": UPSTREAM_COMMIT,
            },
            notes={
                "advisory_only": "upstream sizing/stop prose is evidence, never executable",
                "upstream_version_detected": meta.upstream_version_detected or "n/a",
            },
        ),
    )


def now_utc() -> datetime:
    """Clock source for the adapter (injectable seam for deterministic tests)."""
    return datetime.now(UTC)
