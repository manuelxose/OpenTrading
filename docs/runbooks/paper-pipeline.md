# Runbook — Autonomous PAPER pipeline

How to run, observe and recover the Phase 7 paper pipeline (ADR-0022).

## 1. Quick start (no infrastructure)

One deterministic cycle, everything in-process:

```bash
uv run python -m apps.worker run-once --llm mock
```

Prints pipeline run records, trade lifecycles and the paper account.

Unattended serve with an in-memory bus (demo only — state is not durable):

```bash
uv run python -m apps.worker run --llm mock
```

## 2. Full stack (Redis Streams + PostgreSQL)

```bash
make up                 # docker compose: postgres, redis, minio, falkordb…
uv run alembic upgrade head
OT_PAPER_MODE_ENABLED=true uv run python -m apps.worker run \
    --store postgres --bus redis --llm mock
```

`--llm live` uses the real TradingAgents adapter (pinned upstream; timeouts and
retries enforced). Set `OT_PAPER_LLM_REQUIRED=true` to skip cycles when the LLM
is unavailable.

## 3. Key configuration (OT_* env / .env)

| Variable | Default | Meaning |
|---|---|---|
| `OT_PAPER_INSTRUMENTS` | `EURUSD` | comma-separated watchlist |
| `OT_PAPER_CYCLE_INTERVAL_SECONDS` | `300` | research cadence |
| `OT_PAPER_STARTING_BALANCE` | `100000` | paper account seed |
| `OT_PAPER_POSITION_EQUITY_PCT` | `0.02` | advisory sizing |
| `OT_PAPER_STOP_ATR_RATIO` / `OT_PAPER_TAKE_ATR_RATIO` | `1.5` / `3` | SL/TP distances |
| `OT_PAPER_SLIPPAGE_TICKS` / `OT_PAPER_COMMISSION_BPS` | `1` / `0.5` | venue costs |
| `OT_PAPER_REDIS_STREAM` | `opentrading:events` | stream key |
| `OT_PAPER_MAX_DELIVERIES` | `5` | dead-letter threshold |

## 4. Operations & recovery

- **Workers** — one consumer group per stage (`opentrading-workers:<stage>`).
  On startup each worker reclaims its PEL (XAUTOCLAIM) and reprocesses
  idempotently; see `redis-cli xinfo groups opentrading:events`.
- **Poisoned messages** — archived to `opentrading:events:dead:<group>` after
  `OT_PAPER_MAX_DELIVERIES`; inspect and replay by `XADD`ing the payload back
  if needed.
- **Redis down** — the pipeline logs retries and resumes automatically
  (infinite backoff in serve mode).
- **PostgreSQL down** — stores retry transient `OperationalError`s with
  `pool_pre_ping`; CAS guards make redelivery safe.
- **LLM failures** — audited as `llm.analysis.failed`; the cycle continues
  with the missing-signal fusion policy. Account state is never affected
  (INV-1).
- **Inspect state**:

```sql
SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20;
SELECT * FROM trade_lifecycles ORDER BY updated_at DESC LIMIT 20;
SELECT * FROM paper_accounts;
SELECT * FROM execution_orders  ORDER BY created_at DESC LIMIT 20;
SELECT * FROM execution_positions;
```

## 5. Stop safely

`Ctrl-C` (SIGINT) stops the scheduler and workers. Unacked messages remain in
the PEL and are reclaimed on the next start — the design never requires a clean
shutdown.
