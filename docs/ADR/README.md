# ADR Index — OpenTrading

Architecture Decision Records for the frozen decisions of
`docs/architecture.md` §34 (architecture v1.0, 2026-08-26).

- Template: `.ai/templates/adr.md`
- Workflow: `.ai/workflows/adr-workflow.md`
- Rule: a frozen decision may only be changed by a new ADR (INV-12); violating one
  without an ADR is a blocking defect.

## Accepted

| ADR | Decision | Frozen (§34) | Key invariants |
|---|---|---|---|
| [0001](0001-python-quant-backend.md) | Python as quantitative backend | §34.1 | INV-13 |
| [0002](0002-typescript-command-center.md) | TypeScript Command Center | §34.2 | — |
| [0003](0003-mql4-mt4-bridge-only.md) | MQL4 only for MT4 bridge | §34.3 | INV-5 |
| [0004](0004-tradingagents-llm-committee.md) | TradingAgents as LLM committee | §34.4 | INV-1, INV-2 |
| [0005](0005-qlib-quant-research-platform.md) | Qlib as quant research platform | §34.5 | INV-13 |
| [0006](0006-rd-agent-autonomous-rd-factory.md) | RD-Agent as autonomous R&D factory (offline) | §34.6 | INV-8 |
| [0007](0007-nautilustrader-event-driven-engine.md) | NautilusTrader as event-driven backtest/paper engine | §34.7 | INV-2 |
| [0008](0008-graphiti-temporal-trading-memory.md) | Graphiti as temporal trading memory | §34.8 | INV-3, INV-11 |
| [0009](0009-graphify-development-context-only.md) | Graphify as development context only | §34.10 | INV-11 |
| [0010](0010-postgresql-transactional-truth.md) | PostgreSQL as transactional source of truth | §34.12 | INV-10 |
| [0011](0011-minio-parquet-historical-data.md) | MinIO/Parquet for large historical datasets | §34.13 | INV-10 |
| [0012](0012-redis-streams-initial-event-bus.md) | Redis Streams as initial event bus | §34.14 | INV-15 |
| [0013](0013-langfuse-ai-observability.md) | Langfuse for AI observability | §34.15 | — |
| [0014](0014-prometheus-grafana-ops-observability.md) | Prometheus/Grafana for operational observability | §34.16 | — |
| [0015](0015-deterministic-risk-engine.md) | Deterministic Risk Engine | §34.19 (+§7) | INV-1, INV-4 |
| [0016](0016-mt4-execution-venue-only.md) | MT4 as execution venue only | §34.17 | INV-5 |
| [0017](0017-point-in-time-market-data-semantics.md) | Point-in-time market data semantics (three timestamps, immutable sealed gold, single filter choke point) | §13 + Phase 1 | INV-3, INV-10 |
| [0018](0018-risk-engine-resize-and-denomination.md) | Risk Engine RESIZE decision, exact-arithmetic size gate, exposure denomination | §7 + Phase 5 | INV-1, INV-4 |
| [0019](0019-signal-fusion-calibrated-weights.md) | Signal Fusion Engine: calibrated weights, signed components, disagreement/missing-signal policies, regime-specific models | §16 + Phase 7 | INV-1, INV-2, INV-16 |
| [0020](0020-mt4-execution-protocol.md) | MT4 execution protocol v1.0: versioned ZeroMQ, 13-message vocabulary, idempotency/sequence/expiry/checksum gates, structured error codes, Python emulator | §8 + §34.18 + Phase 6 | INV-2, INV-5, INV-6, INV-7 |
| [0021](0021-broker-reconciliation-and-safe-mode.md) | Broker reconciliation + SAFE_MODE: persisted execution state, OrderStateApplier, startup reconciliation, resolution matrix | §9 + Phase 7 | INV-6 |
| [0022](0022-autonomous-paper-pipeline.md) | Autonomous PAPER pipeline: Redis Streams stages, idempotent run ledger, PEL recovery, LLM failure containment, Nautilus paper venue | §32 Fase 7 + Phase 7 | INV-1, INV-2, INV-6, INV-15 |
| [0023](0023-posttrade-analysis-learning-engine.md) | Post-trade analysis & learning engine: reconciliation-gated deterministic postmortems, canonical metrics in PostgreSQL, artifacts in MinIO, lessons in Graphiti, notes in Obsidian, risk limits immutable | §17 + Phase 7 | INV-1, INV-6, INV-10 |

## Frozen items not yet ADR'd

The remaining §34 items stay frozen at the source document level and will receive ADRs
before any implementation touches them:

- §34.9 — FinMem as inspiration, not a production dependency (cross-referenced in ADR-0008)
- §34.11 — Obsidian as the human knowledge UI (cross-referenced in TARGET_ARCHITECTURE §19)
- §34.20 — Research never auto-promotes to real money (cross-referenced in ADR-0015/0006)

## Later additions

- **ADR-0027 — Standalone XAUUSD RPB Expert Advisor.** Adds `mt4/Experts/XauRpbEA.mq4`
  as a standalone autonomous EA, outside the QuantBridge execution path.
  `QuantBridgeEA.mq4` remains execution-only and INV-5 continues to hold for the
  bridge without exception. The canonical strategy definition stays in Python
  (`research/strategies/xau_rpb/`), with signal-parity tests holding the two
  implementations together.

## Process

1. Draft with `.ai/templates/adr.md` → 2. Principal Architect review → 3. mandatory
reviewers for the change class → 4. merge with the implementation → 5. register here.
