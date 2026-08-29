# ADR-0021: Broker reconciliation and Safe Mode (persisted execution state)

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ execution-mt4 + risk + security + verification for
  execution-sensitive class)

## Context

INV-6 (§9) forbids assuming `send_order() == executed_trade` and mandates that
every restart reconciles database state against broker state, with unexplained
divergence flipping the platform into SAFE_MODE. The MT4 protocol (ADR-0020)
already provides the wire vocabulary — `reconciliation_request` returns account
state, positions, open `order_intent_id`s and per-strategy last-accepted
sequences — but the Core had no authoritative persisted execution state, no
reconciliation engine, and no SAFE_MODE controller.

A crash can strike at any point: after persisting SUBMITTED but before the wire
send, after the send but before the ACK, after the fill but before its events
were persisted, or with duplicated/out-of-order events. Without persisted state
the platform cannot distinguish these cases; without reconciliation it cannot
recover; without SAFE_MODE it could keep opening new positions on top of an
unknown broker reality.

## Decision

**Persist execution state in PostgreSQL** (ADR-0010) and implement a
deterministic reconciliation + SAFE_MODE engine (`engines/execution/`,
migration `0003_execution_state`):

1. **`OrderRecord`** — one authoritative row per `order_intent_id` (the
   idempotency key, INV-2), carrying the full canonical lifecycle
   (CANDIDATE → … → REVIEWED), fill bookkeeping, venue identifiers, and an
   optimistic-concurrency `version` guarded by compare-and-set. SUBMITTED is
   persisted **before** the wire send.
2. **Event application** (`OrderStateApplier`) — the only writer of order
   state; every transition passes `core.domain.state_machines`. Venue events
   carry fingerprints (`message_id:sequence`) stored on the record, so
   duplicated events are no-ops. Out-of-order tolerance: a fill arriving
   before the ACK atomically synthesizes the ACKNOWLEDGED transition; late
   ACK/REJECT/CANCEL after terminal states are no-ops. A cumulative fill
   exceeding the requested quantity (`OVERFILL`) or a fill for a
   cancelled/rejected order is a capital-relevant divergence and raises
   `ExecutionDivergenceError`.
3. **Startup reconciliation** (`ExecutionService.startup_reconciliation`) — the
   §9 procedure in order: (1) load persisted state, (2) query MT4, (3) compare
   open orders, (4) compare positions, (5) compare quantities, (6) compare
   identifiers, (7) reconcile differences. The bridge's `last_sequences` are
   resynced on every run. Every run is persisted in `reconciliation_runs`.
4. **Resolution matrix** (deterministic, unit-tested):
   - *EXPLAINABLE* — auto-healed: ACK inferred from broker open orders
     (`ORDER_ACK_LOST`); a submitted order with no venue trace is closed
     (`ORDER_NEVER_ACKNOWLEDGED`); a broker position proving a lost fill heals
     the order to FILLED (`FILL_EVENT_LOST`); an unmatched position linked to a
     FILLED order is adopted (`POSITION_EVENT_LOST`); a persisted position gone
     at the venue is closed (`POSITION_CLOSED_AT_VENUE`).
   - *WARNING* — recorded, broker is authority for **price**: entry-price
     drift beyond 0.5% adopts the broker price (`PRICE_DRIFT`).
   - *MATERIAL* — reported, never auto-reconciled: unknown broker order
     (`UNEXPECTED_BROKER_ORDER`), unknown broker position
     (`UNEXPECTED_BROKER_POSITION` — e.g. a manual trade at MT4), missing
     acknowledged order (`MISSING_BROKER_ORDER`), quantity/identifier
     mismatches (`QUANTITY_MISMATCH`, `IDENTIFIER_MISMATCH`), overfill
     (`OVERFILL`), and broker unreachable (`BROKER_UNREACHABLE`, including
     `broker_connected=false` in the reconciliation response).
5. **SAFE_MODE** (`SafeModeController`) — entered whenever a run carries
   material discrepancies (or the broker is unreachable at startup): new
   positions are blocked (`SafeModeViolation`), monitoring and reconciliation
   stay available, risk-reducing actions (cancels, position reductions) remain
   available. Entry/exit persist a singleton `safe_mode_state` row, emit
   canonical events (`system.safe_mode.entered/exited`,
   `order.reconciled`, `reconciliation.divergence`), write audit entries, and
   raise an operational alert through an `AlertSink` (transport later).
   A clean reconciliation exits SAFE_MODE automatically.

Adoption matching for positions without a provenance link uses exactly one
candidate (instrument, side, and exact quantity); ambiguity or any unexplained
combination is MATERIAL — the platform prefers SAFE_MODE over guessing.

## Consequences

- The platform can restart at any point of the order lifecycle without losing
  authoritative state (DoD proven by `tests/execution` + `tests/chaos`).
- Duplicate fill detection depends on event fingerprints; a *genuinely
  duplicated* fill with a distinct event id exceeds the requested quantity and
  escalates to SAFE_MODE — deliberately conservative.
- `PostgresExecutionStateStore` is exercised by the docker-gated integration
  suite; unit/chaos suites use the in-memory store with identical semantics.
- Operational entrypoint: `python -m engines.execution.cli reconcile-once`
  (exit 2 = SAFE_MODE/broker unreachable) for cron/systemd alerting.
