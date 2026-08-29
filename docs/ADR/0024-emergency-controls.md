# ADR-0024: Emergency control system — kill switches and dead man switch

- Status: accepted
- Date: 2026-08-28
- Deciders: principal-architect (+ execution-mt4 + risk + security + verification
  for the execution-sensitive class)

## Context

INV-7 and architecture §10 freeze the emergency-control semantics: four kill
levels (`STRATEGY_KILL`, `INSTRUMENT_KILL`, `NO_NEW_POSITIONS`, `EMERGENCY_KILL`
with `CANCEL_PENDING` + optionally flatten) and a dead man switch — on Core ↔ MT4
heartbeat loss, broker-side SL/TP remain, new trades are blocked, and positions
are **never** auto-liquidated for a network drop unless an explicit policy says
so.

Before this ADR the platform had partial pieces: `KillScope` switches on the
LIVE_GATED human-approval path (ADR-0021-era `live_gate`), the SAFE_MODE
controller (ADR-0021), and a transport-level `ConnectionMonitor` that blocks new
commands when the bridge is DOWN. What was missing: a single deterministic
authority with the four §10 levels, dead-man behavior with alerts and audit,
cancel-pending execution, explicit-opt-in flattening, persistence, and an
operator API — all independent of LLM and strategy processes (the Definition of
Done for INV-7).

## Decision

**Implement a dedicated emergency control system** in `engines/execution/`
(migration `0007_emergency_controls`):

1. **`EmergencyLevel`** (core domain enum): `STRATEGY_KILL` (target = strategy
   id), `INSTRUMENT_KILL` (target = symbol), `NO_NEW_POSITIONS` (portfolio),
   `EMERGENCY_KILL` (cancel pending + block entries + flatten only when
   configured).
2. **`EmergencyController`** (`emergency.py`) — the deterministic authority,
   importing nothing from LLM/strategy code:
   - `activate`/`deactivate` persist state (`emergency_controls`), audit
     (`emergency.activated` / `emergency.deactivated`), emit
     `system.emergency.*` domain events and raise operational alerts
     (CRITICAL for EMERGENCY_KILL).
   - `assert_can_enter(strategy_id, instrument_id)` gates new entries against
     all four levels plus the dead-man safe execution state; it is invoked by
     `ExecutionService.submit` before any other gate.
   - `EMERGENCY_KILL` side effects run only through injected deterministic
     executors: `cancel_pending_orders` (always, per §10 `CANCEL_PENDING`) and
     `flatten_positions` **only** when `flatten_on_emergency_kill` is set.
3. **Dead man switch** — `on_heartbeat` (fed by `ExecutionService.drain_events`
   from the MT4 heartbeat stream) and `check_dead_man` (evaluated on the submit
   path, event drains, startup reconciliation and the `check-emergency` CLI):
   - heartbeat loss → `safe_execution_state=true` (persisted in
     `emergency_dead_man`), CRITICAL `DEAD_MAN_SWITCH_ENGAGED` alert, audit
     `dead_man.engaged`, event `system.emergency.heartbeat_lost`;
   - **no broker action at all by default**: existing broker-side SL/TP stay,
     pending orders stay, positions stay — connectivity loss never auto-closes
     anything; `flatten_on_heartbeat_loss` is explicit opt-in only;
   - recovery heartbeat clears the state with `dead_man.restored` + INFO alert.
4. **Emergency closures** — flattening emits offsetting MARKET `OrderIntent`s
   with `strategy_id=CORE-EMERGENCY`; the LIVE_GATED authorizer routes them to
   `assert_emergency_close_authorized` (deterministic policy check) instead of
   the human approval gate, preserving INV-1 while keeping emergency action
   human-independent. Closures remain fully persisted, audited and reconciled.
5. **Operator API** (`apps/api/emergency.py`) — read state and activate /
   deactivate levels behind the LIVE_GATED operator token; the controller
   itself has no dependency on the API process.
6. **Monitor CLI** — `python -m engines.execution.cli check-emergency` drains
   heartbeats and evaluates the dead man switch for a cron/systemd-timer
   cadence; exit 2 when the safe execution state is active.

## Consequences

- Emergency controls now work with every LLM and strategy process down: they are
  a standalone deterministic module over the clock + PostgreSQL + the MT4
  command channel.
- Connectivity loss alone can no longer close positions or strip SL/TP by
  accident; such behavior exists only under explicit configuration, audited.
- `SafeModeAlert` is renamed `OperationalAlert` (compat alias kept) because the
  same alert contract now carries emergency alerts.
- `emergency_controls` keeps deactivated rows for a full audit history.
- DoD evidence: `tests/execution/test_emergency_controller.py` +
  `tests/execution/test_emergency_service_integration.py` cover level gating,
  side-effect opt-in semantics, dead-man engage/restore/idempotency, audit, and
  end-to-end service wiring.
