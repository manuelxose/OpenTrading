# Disaster Recovery — OpenTrading

- **Date:** 2026-08-29
- **Related:** `docs/runbooks/infrastructure.md`, `docs/runbooks/paper-pipeline.md`,
  `docs/OPERATIONS_MANUAL.md`, `engines/execution/service.py`
  (`startup_reconciliation`), ADR-0021 (reconciliation & safe mode),
  ADR-0024 (emergency controls).

---

## 1. Objectives

| Objective | Target | Basis |
|---|---|---|
| RPO — PostgreSQL | ≤ 24 h (daily dumps) | `scripts/backup.sh` daily; switch to continuous WAL archiving (`pg_basebackup`/WAL-G) to tighten to ≤ 5 min before live capital |
| RPO — MinIO (parquet history, artifacts) | ≤ 24 h | nightly `mc mirror` |
| RPO — Redis | not required | cache + event bus: state is replayable; PEL reclaimed on restart; dead letters archived |
| RTO — paper pipeline | ≤ 5 min (auto) | worker reclaims PEL, dead-letters poisoned messages, resumes unattended |
| RTO — execution service | ≤ 15 min + reconciliation | `startup_reconciliation` is mandatory before trading resumes; SAFE_MODE on divergence |
| RTO — full stack | ≤ 4 h | compose recreate + Postgres restore + MinIO mirror + `alembic upgrade head` |

**Status:** targets are set for paper/demo operation. Before live capital the
RPO target must be re-agreed and the restore drill executed at least once per
quarter against a scratch environment.

## 2. What is already built in

- **Authoritative execution state in PostgreSQL** (`execution_orders`,
  `execution_positions`, `reconciliation_runs`, `safe_mode_state`), with
  SUBMITTED persisted **before** the wire send — a crash at any point leaves a
  reconstructible record.
- **Mandatory 7-step restart reconciliation** (`startup_reconciliation`):
  load persisted state → query MT4 → compare open orders / positions /
  quantities / identifiers → reconcile explainable differences → adopt bridge
  sequence numbers. Material unexplained divergence → **SAFE_MODE**
  (new entries blocked; monitoring + risk-reducing actions allowed).
  Broker unreachable at startup → SAFE_MODE with `BROKER_UNREACHABLE`.
- **Dead man switch** (INV-7): heartbeat loss blocks entries and raises a
  CRITICAL alert; broker-side SL/TP remain; flattening is opt-in only.
- **Worker crash recovery**: Redis Streams consumer groups + `XAUTOCLAIM` PEL
  reclaim; per-stage idempotency on `(trace_id, stage)`; dead-letter streams
  `opentrading:events:dead:<group>` after `OT_PAPER_MAX_DELIVERIES`.
- **Poisoned message quarantine** and manual replay by `XADD`.
- **Migrations**: 9 Alembic migrations (`0001`..`0009`), incl. audit-trail
  immutability (append-only triggers).
- **Idempotent fills**: duplicate-fill fingerprints, fill-before-ACK synthesis,
  sequence validation, per-venue `order_intent_id` idempotency.
- **Fail-closed secrets**: prod compose refuses to start with missing secrets.
- **Append-only audit trail**: `audit_events` / `system_events` cannot be
  updated or deleted by any role (migration 0009).

## 3. Backups

```bash
# Daily (schedule via cron/systemd-timer on the backup host):
OT_BACKUP_DIR=/var/backups/opentrading OT_POSTGRES_PASSWORD=… ./scripts/backup.sh
```

- Produces `backups/postgres/opentrading-<UTC stamp>.dump` (pg_dump custom
  format, `--no-owner`) and `backups/minio/buckets/…` (full `mc mirror`).
- Retention: keep `OT_BACKUP_RETENTION` (default 14) PostgreSQL dumps.
- Store backups off-host (rsync/S3), and verify by test-restoring quarterly.
- Hardening before live: switch to WAL archiving (continuous, PITR-capable) and
  encrypt dumps at rest.

## 4. Restore

```bash
OT_RESTORE_DUMP=/var/backups/opentrading/postgres/opentrading-<stamp>.dump \
OT_RESTORE_MINIO_SRC=/var/backups/opentrading/minio/buckets \
OT_RESTORE_FORCE=1 ./scripts/restore.sh
```

- Refuses a non-empty database unless `OT_RESTORE_FORCE=1` (drops/recreates the
  public schema).
- Restores Postgres (as a superuser-capable role), mirrors MinIO, then runs
  `alembic upgrade head`.
- After restore, **always** run `reconcile-once` before allowing trading: the
  restored execution state must be reconciled against the live broker, and any
  divergence will correctly force SAFE_MODE.

## 5. Scenario playbooks

### 5.1 Core crash mid-submit
1. Restart the execution service.
2. `reconcile-once` runs automatically on startup; SUBMITTED-but-unanswered
   orders are compared against broker state and resolved explainably or SAFE_MODE.
3. Verify `reconciliation_runs` (0 material) before clearing SAFE_MODE.

### 5.2 MT4 / broker unavailable
1. Heartbeat loss → dead man switch engages (entries blocked, CRITICAL alert).
2. `check-emergency` exit 2 keeps alerting; cron monitor pages.
3. On return, run `reconcile-once`; safe state exits only on a clean run.
4. SL/TP on open positions were untouched throughout (flattening only if
   explicitly configured).

### 5.3 Material divergence (unexpected broker position / quantity mismatch)
1. SAFE_MODE is already active — do not clear it.
2. Inspect `reconciliation_runs.discrepancies` (code, severity, explanation).
3. Resolve at the broker (operator) or explain in the platform; the next clean
   `reconcile-once` exits SAFE_MODE with an audit trail.

### 5.4 Postgres loss (volume corruption / deleted)
1. Stop app services. Recreate compose (fresh volumes).
2. Restore: `OT_RESTORE_FORCE=1 ./scripts/restore.sh` (dump + MinIO mirror +
   migrations).
3. Start services; run `reconcile-once`; verify `make health`.

### 5.5 MinIO loss
1. Restore buckets via `mc mirror` from backup (or re-run `minio-init` for empty
   schemas, then mirror data buckets).
2. Verify readiness (`OT_MINIO_READINESS_BUCKET`) and re-run paper cycle.

### 5.6 Redis loss (no restore needed)
1. Recreate Redis; the stream starts empty.
2. Restart workers: consumer groups are recreated, PELs are empty, pipeline
   resumes from PostgreSQL state (idempotent stages).
3. Watch `redis_lag` and pipeline error metrics for the first cycles.

### 5.7 Poisoned message loop
1. Identify the dead-lettered entry: `XRANGE opentrading:events:dead:<group> - +`.
2. Fix the cause (bad payload, code bug), redeploy, then replay the payload
   with `XADD opentrading:events … <fields>` if the trade chain is still needed.
3. Do not blindly clear the dead-letter stream: it is evidence.

### 5.8 Host loss / full rebuild
1. Restore from off-host backups (Postgres + MinIO) onto the new host.
2. Re-provision secrets from the SOPS-encrypted store (`scripts/secrets/decrypt.sh`).
3. `make up-prod` (fails closed if any secret is missing).
4. `reconcile-once` before trading; verify all health endpoints.

## 6. Recovery tests (run these; they exist in the suite)

| Mechanism | Test |
|---|---|
| Restart reconciliation + safe mode | `tests/execution/test_broker_reconciler.py`, `tests/chaos/test_restart_recovery.py` |
| Worker crash before ACK / mid-stage | `tests/chaos/test_process_crash.py` |
| Redis / Postgres / MinIO / FalkorDB / LLM outages | `tests/chaos/test_infra_outages.py` |
| Broker partial fills + crash-after-partial | `tests/chaos/test_broker_event_chaos.py` |
| Network partition | `tests/chaos/test_network_partition.py` |
| Live infra restarts (docker) | `tests/chaos/test_live_infra_restart.py` (opt-in `OT_CHAOS_LIVE=1`) |
| Duplicate fills / out-of-order events | `tests/execution/test_order_applier.py` |
| Paper restart recovery | `tests/worker/test_paper_recovery.py` |

Run quarterly: `uv run pytest tests/chaos tests/execution tests/worker/test_paper_recovery.py`
and the live infra restart suite on a staging docker host.

## 7. Checklist for live-capital readiness

- [ ] WAL archiving with PITR (tighten RPO ≤ 5 min)
- [ ] Off-host backup storage + encryption at rest
- [ ] Quarterly restore drill executed and logged
- [ ] `reconcile-once` exit-code alerting wired to paging
- [ ] `check-emergency` cron/systemd-timer in production
- [ ] Prod Prometheus scrapes the core runtime
- [ ] Resource limits in prod compose
- [ ] Real demo broker connected; EA deployed; live lifecycle replayed
- [ ] Fusion weights calibrated (INV-16) before LIVE_AUTO
