# ADR-0005: Qlib as the quantitative research platform

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ quant-research + market-data as supporting)

## Context

The platform needs quantitative research infrastructure: data processing, ML models,
factor evaluation, backtesting, portfolio/risk modelling and experiment tracking. The
decision was frozen in `docs/architecture.md` §34.5 ("Qlib será la plataforma
cuantitativa") and detailed in §4.

## Decision

**Adopt Microsoft Qlib as the quantitative research platform** inside the Quant R&D
runtime (Python 3.11, Linux — INV-13). Qlib supplies the factor/model/experiment
machinery we would otherwise build from scratch (§4). Its experiment-management
abstractions integrate with MLflow, so no custom experiment system is built (§13).

Production never imports Qlib directly: integration goes through our adapters and
canonical domain objects (§15), so Qlib remains replaceable.

## Alternatives considered

- **Build factor/model/backtest tooling from scratch** — rejected: §4 states Qlib
  already covers processing, models, backtesting, analysis and experiment tracking.
- **Use Qlib for order execution or live trading** — rejected: execution is
  NautilusTrader (ADR-0007) and MT4 (ADR-0016); Qlib is research-scoped.
- **Alternative research stacks (e.g. only scikit-learn/lightgbm ad hoc)** — rejected:
  no unified experiment/discipline layer; §19's multiple-testing protection needs a
  systematic experiment registry.

## Consequences

- Positive: mature, MIT-licensed (§28) research platform; reproducibility and
  experiment tracking by default.
- Negative: Qlib's Python 3.10/3.11 compatibility forces the two-runtime split — already
  mandated by INV-13; not a new cost.
- Follow-ups: Phase 9 activates Qlib together with RD-Agent and MLflow; factors/models
  flow through the Validation Factory (§19) before any promotion.

## Validation

- Frozen decision §34.5; §4 (capabilities, environment split); §13 (MLflow).
- `.ai/agents/quant-research.md` scope: `adapters/qlib`, research methodology, leakage
  prevention.
- Repo evidence: no code yet (PRE-00); decision constrains Phase 9 design.
