# Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented)

Implements INV-6 (architecture §9): **never assume `send_order() ==
executed_trade`**.

## What was built

- `core/schemas/execution.py` — contracts: `OrderRecord`, `ExecutionPosition`,
  `ReconciliationDiscrepancy`, `ReconciliationRun`, `SafeModeRecord`,
  `SafeModeAlert`, `StartupOutcome`, event payloads `ReconciliationEvent` and
  `SafeModeEvent`.
- `core/domain/enums.py` — `DiscrepancyCode`, `SafeModeReason`, `SafeModeAction`.
- `core/events/registry.py` — `order.cancelled`, `order.reconciled`,
  `reconciliation.divergence`, `system.safe_mode.entered`,
  `system.safe_mode.exited`.
- `engines/execution/` — `persistence.py` (PostgreSQL tables
  `execution_orders`, `execution_positions`, `reconciliation_runs`,
  `safe_mode_state`; in-memory + Postgres stores with compare-and-set),
  `applier.py` (canonical transitions, write-before-send SUBMITTED,
  duplicate-event fingerprints, fill-before-ACK synthesis, overfill
  divergence), `reconciler.py` (deterministic compare-and-heal over the five
  §9 axes), `safe_mode.py` (gate: no new positions; monitoring, reconciliation
  and risk-reducing actions allowed; event + audit + alert), `service.py`
  (submit path + 7-step `startup_reconciliation()`), `cli.py`
  (`reconcile-once`, exit 2 on SAFE_MODE/unreachable broker).
- `migrations/versions/0003_execution_state.py` — mirrors the tables.
- `adapters/mt4/broker.py` — `open_manual_position()` (simulate a human trade
  at MT4 for reconciliation testing).

## State machine

The canonical `OrderState` machine (`core/domain/state_machines.py`) is the
single authority for transitions; the applier synthesizes the missing
`ACKNOWLEDGED` transition atomically when fills arrive first, and never
regresses terminal states on stale events.

## Reconciliation resolution matrix

| Severity | Discrepancy | Resolution |
|---|---|---|
| EXPLAINABLE | `ORDER_ACK_LOST` | heal to ACKNOWLEDGED |
| EXPLAINABLE | `ORDER_NEVER_ACKNOWLEDGED` | CANCELLED → RECONCILED |
| EXPLAINABLE | `FILL_EVENT_LOST` | heal to FILLED from broker position |
| EXPLAINABLE | `POSITION_EVENT_LOST` | link/adopt position |
| EXPLAINABLE | `POSITION_CLOSED_AT_VENUE` | close position |
| WARNING | `PRICE_DRIFT` | adopt broker price |
| MATERIAL | `UNEXPECTED_BROKER_ORDER` / `UNEXPECTED_BROKER_POSITION` / `MISSING_BROKER_ORDER` / `QUANTITY_MISMATCH` / `IDENTIFIER_MISMATCH` / `OVERFILL` / `BROKER_UNREACHABLE` | **SAFE_MODE** |

## DoD evidence

- `tests/execution/` — store CAS semantics; full lifecycle; duplicate fill /
  duplicate ACK no-ops; fill-before-ACK; out-of-order reject/ack after fill;
  overfill divergence; every reconciler matrix row; SAFE_MODE gate + alert;
  7-step startup service (clean / unreachable / recovery / divergence).
- `tests/chaos/` — over real ZeroMQ loopback: crash after submit (broker never
  saw → explainable closure), crash before ACK (broker filled → healed FILLED),
  MT4 restart (resync + re-entry), idempotent re-submit never doubles a trade,
  network partition (SAFE_MODE → recovery), unexpected manual broker position
  (SAFE_MODE + alert).
- `tests/integration/test_execution_state_integration.py` — Postgres store
  roundtrip (docker-gated).

See `docs/ADR/0021`.
