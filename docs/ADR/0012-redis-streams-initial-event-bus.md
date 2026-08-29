# ADR-0012: Redis Streams as the initial event bus

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ backend-platform + infra-sre as supporting)

## Context

The platform is event-driven and needs a message backbone. The decision was frozen in
`docs/architecture.md` §34.14 ("Redis Streams será el bus inicial") and detailed in
§13–§14.

## Decision

**Redis Streams is the initial event bus**, with Redis also serving cache, locks, rate
limits, ephemeral state, and worker coordination (§13). Kafka/Redpanda are explicitly
deferred ("Más adelante", §2) until operational scale justifies them.

All domain events use the standard envelope (INV-15):

```python
class DomainEvent:
    schema_version: str
    event_id: UUID
    trace_id: UUID
    event_time: datetime
    ingested_at: datetime
    producer: str
    payload: dict
    provenance: dict
```

Event vocabulary (§14): `market.snapshot.created`, `research.requested/completed`,
`quant.signal.created`, `llm.signal.created`, `signal.fused`, `risk.approved/rejected`,
`order.intent.created/submitted/acknowledged/partially_filled/filled/rejected`,
`position.updated`, `trade.closed`, `postmortem.completed`, `memory.episode.created`,
`strategy.candidate.created/promoted/retired`, `experiment.created/completed`,
`system.safe_mode.entered/exited`.

## Alternatives considered

- **Kafka/Redpanda from day one** — rejected by §2: Redis Streams is sufficient
  initially; Kafka adds operational cost without a scale-driven reason.
- **Synchronous in-process calls only** — rejected: workers, replay, and the
  post-trade loop need decoupled consumers; reconciliation depends on the event trail.
- **Celery/RabbitMQ as the backbone** — rejected: Redis Streams is frozen (§34.14) and
  avoids a second broker; changing it requires a new ADR (INV-12).

## Consequences

- Positive: one Redis deployment covers cache + bus; simple consumer groups; envelope
  guarantees auditability and schema evolution.
- Negative: Redis Streams is not a durable high-throughput log — accepted until the
  explicit Kafka trigger; event replay needs our own retention discipline.
- Follow-ups: Phase 0 defines the envelope contract (architecture-wide); Phase 1
  provisions Redis; consumers are idempotent by `event_id`.

## Validation

- Frozen decision §34.14; §14 (envelope + event list); §13 (Redis roles).
- INV-15; `.ai/agents/backend-platform.md` (event bus wiring, envelope mandatory).
- Repo evidence: no bus exists yet (PRE-00).
