# ADR-0010: PostgreSQL as the transactional source of truth

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ backend-platform + market-data for schema work)

## Context

The platform needs a transactional store that answers "what is the system's state right
now" with ACID guarantees and a full audit trail. The decision was frozen in
`docs/architecture.md` §34.12 ("PostgreSQL será la fuente transaccional de verdad") and
detailed in §13.

## Decision

**PostgreSQL + TimescaleDB is the transactional source of truth** for (§13):

```text
accounts, strategies, strategy_versions, risk_policies, signals, trade_proposals,
risk_decisions, order_intents, broker_orders, executions, positions, trades,
portfolio_snapshots, system_events, audit_events, promotion_decisions
```

TimescaleDB hypertables cover time-series transactional data (snapshots, events).
Reconciliation (§9) loads DB state and compares it to broker state on every restart.

## Alternatives considered

- **Postgres for everything including heavy market data** — rejected: §13/INV-10 split
  stores by purpose; ticks/bars go to Parquet/MinIO (ADR-0011).
- **MongoDB / document store as truth** — rejected: order/position state machines (§9)
  need transactional integrity and relational audit queries; Postgres is frozen (§34.12).
- **SQLite** — rejected: single-writer, no hypertable equivalent, insufficient for a
  multi-worker platform.

## Consequences

- Positive: ACID for money-adjacent records; proven audit/trace tooling; TimescaleDB
  adds time-series efficiency without a second DB engine.
- Negative: schema migrations become architecture-wide changes — mandatory
  `principal-architect` review on domain contracts (ROUTING_RULES).
- Follow-ups: Phase 1 provisions Postgres/Timescale; domain migrations ship with
  Phase 0 schemas.

## Validation

- Frozen decision §34.12; §13 table (transactional scope); §9 (reconciliation reads
  DB state); INV-10.
- `.ai/agents/backend-platform.md`: migrations and Postgres scope; forbidden ad-hoc DB
  writes.
- Repo evidence: no database exists yet (PRE-00).
