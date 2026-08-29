# Observability alert runbook

All pages require an incident record with the firing labels, first-seen time, and an
affected `trace_id` when one exists. Never bypass SAFE_MODE to clear an alert.

## MT4 heartbeat missing

Confirm `time() - opentrading_mt4_last_heartbeat_timestamp_seconds`, check the private
WireGuard/ZeroMQ path, and keep new orders blocked until heartbeat and reconciliation pass.

## Stale market data

Identify the `source` label, stop new decisions using that feed, inspect ingest health, and
resume only after timestamps advance and point-in-time validation succeeds.

## Unexpected broker position

Keep SAFE_MODE active. Run broker reconciliation, compare venue ticket/quantity/symbol to
PostgreSQL, and escalate to the execution owner before adopting or flattening any position.

## Daily loss threshold

Confirm account equity and realized PnL against the broker, verify the deterministic daily
loss policy, and leave `NO_NEW_POSITIONS` active. Human risk approval is required to resume.

## Drawdown threshold

Validate peak equity and current marks, halt promotion/new entries, and escalate to Risk.

## Queue backlog

Inspect lag by consumer group, pending delivery counts and dead letters. Restore the failing
worker or Redis dependency; do not trim an unprocessed stream.

## LLM provider failure

Filter Langfuse by provider/status and inspect error spans. Research may degrade to the
configured deterministic path; LLM failures must never weaken risk checks.

## PostgreSQL failure

Check `pg_up`, storage, connections and recent migrations. Stop writes, preserve volumes,
and restore from the documented backup path if required.

## Redis failure

Check `redis_up`, authentication, memory and persistence. Workers should retry safely; do
not delete pending entries or recreate consumer groups until recovery impact is understood.
