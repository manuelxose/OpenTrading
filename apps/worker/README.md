# apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022)

Redis Streams consumer groups (INV-15) drive the research → trade → post-trade
pipeline end to end in PAPER mode. No real broker execution is possible in this
milestone.

```
market.snapshot.created / research.requested (scheduler)
   research        Graphiti memory + TradingAgents + quant → ResearchBundle
   fusion          calibrated FusionEngine → FusedSignal
   proposal        deterministic sizing (LLMs never size) → TradeProposal
   risk            deterministic Risk Engine → RiskDecision
   order-intent    UUIDv5 idempotency key → OrderIntent (persisted, INV-6)
   execution       Nautilus paper venue → ExecutionReports → Position
   positions       SL/TP monitoring → close proposals (same canonical chain)
   accounting      sole writer of PaperAccountRecord (INV-1)
   posttrade       closed-and-reconciled gate → deterministic metrics + 4 sinks
                   (PostgreSQL / MinIO / Graphiti / Obsidian) → order REVIEWED
```

## Run

```bash
uv run python -m apps.worker run-once --llm mock          # one cycle, in-process
uv run python -m apps.worker run --llm mock               # serve + workers (in-memory bus)
OT_PAPER_MODE_ENABLED=true uv run python -m apps.worker run \
    --store postgres --bus redis --llm live                # production wiring
```

- `--llm mock|live|off` — TradingAgents adapter (mock is deterministic).
- `--store memory|postgres`, `--bus memory|redis`, `--data-source synthetic|repository`.
- `--artifacts memory|minio` — post-trade artifact sink (MinIO uses `OT_MINIO_*`).
- Watchlist/cadence/limits: `OT_PAPER_*` settings; post-trade sinks: `OT_POSTTRADE_*`
  (see `.env.example`).

## Delivery & recovery

- One stream (`opentrading:events`), one consumer group per stage.
- Startup: reclaim PEL entries (XAUTOCLAIM) → idempotent redelivery via the
  `pipeline_runs` ledger.
- Poisoned messages (> `max_deliveries`) → per-group dead-letter stream.
- Redis/PostgreSQL outages: retry with backoff; the pipeline resumes on its own.
- Failed LLM analysis: contained, audited, never touches account state.

## Layout

| Module | Responsibility |
|---|---|
| `bus.py` | Redis Streams + `InMemoryStreamBus`, reconnect, PEL recovery |
| `persistence.py` | `pipeline_runs` / `trade_lifecycles` / `paper_accounts` / `trade_contexts` stores (migrations 0004/0005) |
| `ledger.py` | net positions, fills → TradeOutcome, observed price path, account/portfolio views |
| `lifecycle.py` | CAS-guarded `TRADE_LIFECYCLE_TRANSITIONS` helper |
| `pipeline.py` | stage graph + `StageWorker` consumer loop |
| `scheduler.py` | `UnattendedPaperRunner` (serve / run-once) |
| `sources.py` | repository or synthetic snapshot sources |
| `producers.py` | baseline quant + memory-context producers |
| `config.py` | `PaperPipelineConfig`, paper risk policy, venue factory |
| `cli.py` | `python -m apps.worker` |
| `stages/posttrade.py` | reconciliation gate + `engines/posttrade` orchestration |

See `docs/architecture/PHASE7_AUTONOMOUS_PAPER.md`,
`docs/architecture/PHASE7_POSTTRADE_LEARNING.md`, ADR-0022 and ADR-0023.
