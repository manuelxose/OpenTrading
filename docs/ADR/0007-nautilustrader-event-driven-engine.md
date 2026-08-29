# ADR-0007: NautilusTrader as the event-driven backtest/paper engine

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ trading-backtest + risk + verification for
  engine changes)

## Context

Backtesting, paper trading and live execution must share one event/execution model;
three hand-written implementations (`backtest_strategy.py`, `paper_strategy.py`,
`live_strategy.py`) would diverge. The decision was frozen in
`docs/architecture.md` §34.7 ("Nautilus será el motor event-driven/backtest/paper") and
detailed in §5.

## Decision

**Adopt NautilusTrader as the event-driven engine** responsible for (§5): simulation
clock, market events, simulated orders, fills, fees, slippage, positions, portfolio,
historical replay, paper trading, and strategy lifecycle — **not** for generating LLM
arguments.

**Canonical crossing object (INV-2):**

```text
Signal → Risk → OrderIntent
                  ├── BACKTEST → Nautilus simulated venue
                  ├── PAPER    → Nautilus simulated venue
                  └── LIVE     → MT4 Execution Adapter
```

The system object is always `OrderIntent`, never `MT4Order`.

## Alternatives considered

- **Three parallel strategy implementations** — rejected explicitly by §5/INV-2:
  guaranteed divergence between backtest, paper and live.
- **Qlib's backtester as the execution engine** — rejected: Qlib is research-scoped
  (ADR-0005); §5 assigns execution/parity to Nautilus.
- **Custom event-driven engine** — rejected: §5 states Nautilus solves exactly the
  event/execution consistency problem across research, simulation and production.

## Consequences

- Positive: one code path for BACKTEST/PAPER/LIVE parity; deterministic replay
  capability; reusable strategy lifecycle.
- Negative: LGPL-3.0 license (§28) — Nautilus is kept as an independent dependency,
  its code is never copied into our core.
- Follow-ups: Phase 4 delivers the adapter (`MarketSnapshot`/`Strategy`/`OrderIntent`/
  `ExecutionReport`) with the DoD "two runs → deterministic results".

## Validation

- Frozen decision §34.7; §5 (responsibilities, OrderIntent rule); INV-2.
- `.ai/agents/trading-backtest.md`: scope `adapters/nautilus`; forbidden divergent
  implementations and cost-free backtests.
- Repo evidence: no engine code yet (PRE-00).
