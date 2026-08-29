# Operations Manual — OpenTrading

- **Audience:** operators of the platform (trading operators, risk owners,
  quant researchers).
- **Guiding rule (INV-1):** LLMs research, argue and propose; deterministic
  code decides whether a trade may execute. No operational procedure may grant
  an LLM authority over capital, limits or operating mode.

---

## 1. Operating modes (INV-8)

Exactly five modes exist; the mode is fixed at process start and **can never be
changed at runtime** by an API call, an LLM or a strategy.

| Mode | Who runs | Trading? |
|---|---|---|
| `RESEARCH` | researchers | no — data + analysis only |
| `BACKTEST` | quant R&D | simulated Nautilus backtests only |
| `PAPER` | autonomous pipeline | simulated venue (`NautilusPaperExecutor`), no real money |
| `LIVE_GATED` | execution service + operator | real MT4, **every order needs explicit human approval** |
| `LIVE_AUTO` | promoted strategies | real MT4 without per-trade approval, bounded by the deterministic live-auto registry |

- The worker (`apps.worker`) refuses to start in `LIVE_GATED` / `LIVE_AUTO`
  (trust-zone guard, ADR-0025).
- `LIVE_AUTO` additionally requires an explicit recorded operator promotion of
  each strategy and `OT_LIVE_AUTO_ENABLED=true` with
  `OT_LIVE_AUTO_MAX_STRATEGIES ≥ 1`, `OT_LIVE_AUTO_MAX_CAPITAL > 0`,
  `OT_LIVE_AUTO_MAX_LOSS > 0`.

## 2. Daily runbook — development / staging

```bash
make setup            # uv sync --all-groups (Python 3.12)
make up               # docker compose stack + migrations + MinIO buckets
make health           # infra_health.py probe of all dependencies
make migrate          # alembic upgrade head  (run as ot_migrator in prod)
make lint typecheck test   # static gates + full suite
```

One deterministic paper cycle, fully in-process (no infra):

```bash
uv run python -m apps.worker run-once --llm mock
```

Full paper pipeline on the real stack (Redis Streams + PostgreSQL):

```bash
OT_PAPER_MODE_ENABLED=true uv run python -m apps.worker run \
    --store postgres --bus redis --llm mock|live
```

See `docs/runbooks/paper-pipeline.md` for recovery semantics (PEL reclaim,
dead-letter streams, `OT_PAPER_MAX_DELIVERIES`).

## 3. Live operations (LIVE_GATED)

Live mode mounts the operator API behind `OT_LIVE_OPERATOR_TOKEN`
(`Authorization: Bearer <token>`; ≥32 chars — shorter tokens are rejected at
config load). The approval signing key `OT_LIVE_APPROVAL_SIGNING_KEY` (≥32
chars) must come from the secret store.

| Endpoint | Purpose |
|---|---|
| `GET  /api/v1/live-gated/approvals/{id}` | inspect approval status |
| `POST /api/v1/live-gated/approvals/{id}/approve` | human approves (HMAC-bound, TTL `OT_LIVE_APPROVAL_TTL_SECONDS`) |
| `POST /api/v1/live-gated/approvals/{id}/reject` | human rejects |
| `POST /api/v1/live-gated/kill-switches` | activate kill (`STRATEGY`/`INSTRUMENT`/`PORTFOLIO`/`EMERGENCY`) |
| `DELETE /api/v1/live-gated/kill-switches/{scope}` | clear kill |
| `GET/POST /api/v1/live-auto/*` | LIVE_AUTO registry, promotions, PnL ledger |
| `POST /api/v1/emergency/*` | emergency controls in LIVE_GATED/LIVE_AUTO |

Live approval lifecycle: order intent → `WAITING_FOR_HUMAN` (quote snapshot,
price context hashed into the approval) → human approve → signature bound to
intent + expiry (`live_approval_ttl_seconds`) → `consumed` once → order sent.
Material market drift or an expired approval forces revalidation and a **new**
human decision.

## 4. Emergency control system (INV-7)

Levels: `STRATEGY_KILL` / `INSTRUMENT_KILL` (targeted) → `NO_NEW_POSITIONS` →
`EMERGENCY_KILL` (cancel pending + block entries; flatten only when
`OT_EMERGENCY_FLATTEN_ON_KILL=true`).

- **Dead man switch:** Core ↔ MT4 heartbeat loss (timeout
  `OT_EMERGENCY_HEARTBEAT_TIMEOUT_SECONDS`) blocks new entries, keeps broker
  SL/TP untouched, raises a CRITICAL alert and persists a safe execution
  state. Positions are **never** auto-closed by connectivity loss unless
  `OT_EMERGENCY_FLATTEN_ON_HEARTBEAT_LOSS=true`.
- **Cron-able monitor:** `uv run python -m engines.execution.cli check-emergency`
  exits `2` when the safe state is engaged — wire it to alerting.
- **Flatten/cancel** are executed only through the deterministic emergency
  authorizer (`assert_emergency_close_authorized`), stamped with
  `CORE-EMERGENCY`, fully persisted and reconciled.

## 5. Reconciliation (INV-6 — mandatory)

- `uv run python -m engines.execution.cli reconcile-once` — the 7-step restart
  procedure (load persisted state → query MT4 → compare orders/positions/
  quantities/identifiers → reconcile explainable differences → adopt bridge
  sequences). Exit `0` = clean; exit `2` = broker unreachable or SAFE_MODE
  entered → page.
- SAFE_MODE blocks new entries but allows monitoring, reconciliation and
  risk-reducing actions. Exit SAFE_MODE only via a clean reconciliation run.
- Run reconciliation after **every** Core or MT4 restart and on a schedule
  (e.g. hourly) in live modes.

## 6. Monitoring & alerting

- **Prometheus metrics** (`/metrics`, `core/observability/metrics.py`):
  pipeline stage durations/errors, execution observations
  (`execution_fill_latency`, rejections), MT4 heartbeat age
  (`mt4_heartbeat_age_seconds`), reconciliation gauges
  (`unexpected_broker_positions`), Redis lag per consumer group.
- **Grafana:** dashboards per `docs/runbooks/observability-alerts.md`; alert on:
  safe mode engaged, reconciliation divergence, MT4 heartbeat age >
  timeout, dead-letter growth, pipeline error rate, Redis lag.
- **Langfuse:** one trace per pipeline stage, W3C trace id derived from the
  domain `trace_id`; metadata passes a 17-key allowlist; degrades to a no-op
  on failure.
- **Logging:** redacting filter installed in API, worker and execution
  processes; secrets masked even if a handler is misconfigured.
- **Readiness:** `GET /readyz` probes Postgres, Redis, MinIO, FalkorDB,
  ClickHouse, Langfuse, MLflow, Prometheus, Grafana (configurable via
  `OT_*_URL` settings).

## 7. Maintenance tasks

| Task | Cadence | Command / notes |
|---|---|---|
| Migrations | per release | `uv run alembic upgrade head` as `ot_migrator` (prod) |
| Backups | daily (prod) | `scripts/backup.sh` — pg_dump custom format + MinIO mirror; keep `OT_BACKUP_RETENTION` dumps |
| Restore drill | quarterly | `scripts/restore.sh` into a scratch Postgres — see DISASTER_RECOVERY |
| Secret rotation | per policy | re-encrypt with `scripts/secrets/encrypt.sh`; rotate DB/Redis/MinIO credentials via `002-roles.sh`/ACL/policies on fresh init |
| Emergency check | continuous | `check-emergency` via cron/systemd-timer |
| Reconciliation | after restarts + hourly in live | `reconcile-once` exit-code monitor |
| Dependency audit | per push (CI) | gitleaks + pip-audit; review `external-lock.yaml` quarterly |
| Dead-letter review | weekly | `XRANGE opentrading:events:dead:*` — replay by `XADD` after fixing the cause |

## 8. Troubleshooting quick map

| Symptom | First checks |
|---|---|
| API 401 on live endpoints | token ≥32 chars? correct `Bearer ` header? |
| Worker not starting in live modes | expected — trust-zone guard; live modes run in the execution service, not the LLM worker |
| `pipeline.stage.failed` flood | `pipeline_runs` error column; PEL pending count; dead-letter streams |
| SAFE_MODE engaged | `reconciliation_runs` for material discrepancy codes; `check-emergency` exit code; `mt4_heartbeat_age_seconds` |
| Paper account drift | `execution_orders` vs `execution_positions` vs `trade_lifecycles`; rerun `reconcile-once`-equivalent checks; ledger reattachment on restart (`positions._reattach_stop_levels`) |
| Graphiti search empty after restart | known limitation (in-process envelope index) — re-ingest episodes |
| Quant-R&D fails at startup | env guard or Python version guard (3.11 required) — see error text |

## 9. Never do

- Never hand broker credentials, MT4 credentials, execution sockets or secret
  material to an LLM process, prompt, Langfuse payload or Obsidian vault.
- Never expose the ZeroMQ channels or the API to the internet (private network /
  WireGuard only; prod compose publishes no ports).
- Never change `OT_OPERATING_MODE` at runtime; a mode change is a redeploy with
  an audit record.
- Never `UPDATE`/`DELETE` from `audit_events` / `system_events` — the database
  now rejects it (migration 0009).
- Never size an order from LLM output — quantities are computed by the Risk
  Engine only (INV-1).
