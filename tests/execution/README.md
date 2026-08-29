# tests/execution — idempotency, reconciliation, state machine (INV-6)

Deterministic DoD suite for broker reconciliation and Safe Mode
(`engines/execution`), run without sockets or PostgreSQL:

- `test_execution_store.py` — authoritative store semantics: creation order,
  compare-and-set (`StaleStateError`), positions, runs, SAFE_MODE singleton.
- `test_order_applier.py` — full canonical lifecycle CANDIDATE→REVIEWED;
  crash-restart persistence; duplicate fill/ACK no-ops; fill-before-ACK
  synthesis; out-of-order reject/ack after fill; overfill divergence.
- `test_broker_reconciler.py` — the §9 resolution matrix: ack lost, never
  acknowledged, fill/position event lost, position closed at venue, price
  drift, unexpected broker order/position, quantity/identifier mismatch,
  disconnected broker.
- `test_safe_mode_controller.py` — SAFE_MODE gate (new entries blocked;
  monitoring / reconciliation / risk-reducing allowed), events, audit, alerts.
- `test_execution_service.py` — the 7-step startup reconciliation and the
  write-before-send submit path against a protocol-level fake client.

Same `order_intent_id` 100× → never more than one trade (emulator-level proof
lives in `tests/unit/mt4/test_lifecycle.py`; chaos-level restarts in
`tests/chaos/`).
