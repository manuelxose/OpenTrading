# engines/execution — Broker reconciliation & Safe Mode (INV-6)

The execution engine never assumes `send_order() == executed_trade`:

- `persistence.py` — PostgreSQL tables (`execution_orders`,
  `execution_positions`, `reconciliation_runs`, `safe_mode_state`) plus
  `InMemoryExecutionStateStore` / `PostgresExecutionStateStore`. Every order
  update is a compare-and-set on the record `version`.
- `applier.py` — the only writer of `OrderRecord` state: canonical transitions,
  SUBMITTED persisted *before* the wire send, duplicate-event fingerprints,
  fill-before-ACK synthesis, overfill divergence detection.
- `reconciler.py` — the deterministic §9 compare-and-heal pass over open
  orders, positions, quantities and identifiers. EXPLAINABLE discrepancies are
  healed; MATERIAL ones are reported, never auto-reconciled.
- `safe_mode.py` — SAFE_MODE controller: blocks NEW_ENTRY, allows monitoring,
  reconciliation and risk-reducing actions; emits event + audit + alert.
- `emergency.py` + `emergency_persistence.py` — emergency control system
  (INV-7, §10): the four levels STRATEGY_KILL / INSTRUMENT_KILL /
  NO_NEW_POSITIONS / EMERGENCY_KILL plus the dead man switch. Heartbeat loss
  enters a safe execution state (CRITICAL alert, new entries blocked,
  broker-side SL/TP untouched, no auto-close unless the policy explicitly
  enables flattening). Fully audited and independent of LLM and strategy
  processes. Migration `0007_emergency_controls`.
- `service.py` — the submit path and `startup_reconciliation()` (load →
  query MT4 → compare → reconcile → SAFE_MODE).
- `cli.py` — `reconcile-once`: run the startup procedure from a cron/systemd
  hook against PostgreSQL + MT4 settings; `check-emergency`: dead man switch
  monitor for a cron/systemd-timer cadence.

State machine authority lives in `core/domain/state_machines.py`; contracts in
`core/schemas/execution.py`; migration `0003_execution_state` mirrors the
tables. See `docs/ADR/0021` and
`docs/architecture/PHASE7_EXECUTION_STATE.md`.
