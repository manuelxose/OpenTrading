# Phase 7 — Autonomous PAPER pipeline

Implemented 2026-08-27 (ADR-0022). The entire research-to-trade lifecycle runs
unattended in PAPER mode over Redis Streams, fully persisted and auditable.

## The lifecycle

```
Market Data ──► MarketSnapshot ──► Graphiti memory ──► TradingAgents
                                                    ──► QuantSignal (baseline)
      ──► FusionInputs ──► FusedSignal ──► TradeProposal
      ──► Risk Engine ──► RiskDecision ──► OrderIntent
      ──► Nautilus paper venue ──► ExecutionReport(s) ──► Position
      ──► SL/TP close ──► TradeOutcome ──► PostTradeReview ──► memory episode
```

Every arrow is a canonical `DomainEvent` on the stream; every payload and
envelope carries the trace id.

## Components

| Component | Path | Responsibility |
|---|---|---|
| Contracts | `core/schemas/pipeline.py`, `fusion.py` (`ResearchBundle`) | `PipelineRunRecord`, `TradeLifecycle`, `PaperAccountRecord`, research bundle |
| State machine | `core/domain/state_machines.py` | `TRADE_LIFECYCLE_TRANSITIONS` |
| Bus | `apps/worker/bus.py` | Redis Streams + consumer groups, PEL recovery, dead-letter, reconnect |
| Persistence | `apps/worker/persistence.py`, migration `0004` | run ledger, lifecycles, paper account (CAS) |
| Ledger | `apps/worker/ledger.py` | net positions, fills → outcomes, account/portfolio views |
| Stages | `apps/worker/stages/` | ingest, research, fusion, proposal, risk, order intent, execution, positions, accounting, posttrade |
| Paper venue | `adapters/nautilus/paper.py` | one-shot Nautilus backtest per order (INV-2 mapping + cost models) |
| Runner | `apps/worker/scheduler.py`, `pipeline.py`, `cli.py` | unattended serve / run-once, stage workers |
| Sources | `apps/worker/sources.py` | repository (PIT) or synthetic (seeded) snapshots |

## Operating modes

```bash
uv run python -m apps.worker run-once --llm mock   # one synchronous cycle
uv run python -m apps.worker run                   # unattended serve (Redis Streams)
```

Watchlist, cadence, sizing and risk limits come from `OT_*` settings /
`.env.example`; defaults ship in `apps/worker/config.py`.

## Recovery guarantees

| Failure | Mechanism |
|---|---|
| Worker restart | PEL reclaim (`XAUTOCLAIM`) + idempotent run ledger |
| Redis reconnect | per-command retry + backoff, infinite in unattended mode |
| Database reconnect | `pool_pre_ping` + `OperationalError` retry, CAS everywhere |
| Model timeout / TradingAgents crash | contained in the research stage; bundle carries `llm_error`; fusion missing-signal policy |
| Poisoned messages | dead-lettered after `max_deliveries`, archived for audit |

A failed LLM analysis can never mutate `paper_accounts` (INV-1): only
deterministic execution events feed the accounting stage. No real broker
execution exists in this milestone: the execution stage refuses every mode
other than PAPER.

## Definitions of Done (verified by tests)

- `tests/worker/test_paper_pipeline_e2e.py` — full chain incl. SL/TP close →
  `TradeOutcome` → postmortem → memory episode; trace_id propagation; every
  stage persisted; audit entries.
- `tests/worker/test_paper_recovery.py` — restart redelivery idempotency,
  poisoning → dead-letter, LLM failure containment, mode guard, DB retry.
- `tests/worker/test_paper_bus.py`, `test_paper_persistence.py`,
  `test_paper_ledger.py`, `tests/unit/worker/test_paper_contracts.py`,
  `tests/unit/nautilus/test_paper_executor.py`.
