# ADR-0004: TradingAgents as the LLM research committee

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ ai-trading-systems + risk + security + verification
  for the LLM-to-trading boundary class)

## Context

The platform needs a qualitative, multi-agent LLM research capability. The decision was
frozen in `docs/architecture.md` §34.4 ("TradingAgents será el comité LLM") and detailed
in §3.

## Decision

**Adopt TauricResearch/TradingAgents as the LLM research committee**, integrated behind
our own adapter — never by rewriting it and never by importing its internals into the
domain (§3):

```text
adapters/tradingagents/{client.py, mapper.py, prompts/, schemas.py, evaluator.py}
```

- Input to TradingAgents: `ResearchRequest(instrument, as_of, market_snapshot,
  portfolio_context, memory_context, regime_context)`.
- Output from TradingAgents: our canonical `LLMSignal` (direction, conviction, thesis,
  risks, catalysts, horizon, evidence, model_metadata).
- LangGraph remains its internal orchestrator (§2).

**Hard constraints (INV-1, INV-2):** its LLM-produced position sizing, stop-loss and
BUY/SELL suggestions are advisory only. `LLM position_sizing ≠ executable size`,
`LLM stop_loss ≠ automatically accepted stop`, `LLM BUY ≠ market order`. Its
`PortfolioDecision` is not an execution layer.

## Alternatives considered

- **Build our own multi-agent committee from scratch** — rejected: §3 explicitly
  states TradingAgents' current state (specialized analysts, bull/bear debate, risk
  analysts, portfolio manager, structured output) is already more complete.
- **Use TradingAgents as the broker-facing layer** — rejected: violates INV-1/INV-2;
  the LLM never holds authority over capital.
- **No qualitative layer (quant-only)** — rejected: §16 requires the quant-vs-LLM
  comparison; the fusion weight may drop to zero only through calibration evidence.

## Consequences

- Positive: mature debate/tool/analyst machinery for free; adapter isolates us from its
  internals and its evolution.
- Negative: LLM cost/latency/nondeterminism — mitigated by Langfuse observability (§22)
  and the LLM evaluation harness (§21).
- Follow-ups: Phase 2 integrates read-only (`MarketSnapshot → LLMSignal`) with the DoD
  "no code path from TradingAgents to MT4".

## Validation

- Frozen decision §34.4; §3 (adapter layout, canonical types); §2 decision table.
- INV-1, INV-2; `.ai/agents/ai-trading-systems.md` (scope + forbidden list).
- License check: Apache-2.0 (§28) — compatible with adapter integration.
