# tests/chaos — dedicated chaos/recovery suite

Reproducible automated scenarios proving the DoD: **the platform survives
expected infrastructure failures without creating uncontrolled broker
exposure.**

Two flavors:

- **Deterministic fault injection** (always runs, no docker): every outage is
  injected at a real seam — the actual `RedisStreamBus` retry loop, the actual
  stage/worker redelivery path, the actual reconciliation and dead-man
  procedures — with scripted recoveries.
- **Real container restarts** (`test_live_infra_restart.py`): opt-in, actually
  terminates/restarts the docker-compose services. Run with
  `OT_CHAOS_LIVE=1 uv run pytest -m integration tests/chaos/test_live_infra_restart.py`.

## Scenario matrix

| # | Failure injected | Test (file → test) | Validations asserted |
|---|---|---|---|
| 1 | Redis termination | `test_infra_outages.py::TestRedisTermination` | no event lost, exactly-once delivery after recovery, clean `BusUnavailableError` in bounded mode |
| 2 | PostgreSQL restart | `test_infra_outages.py::TestPostgresRestart`, `test_live_infra_restart.py::TestLiveRestarts::test_postgres_restart_preserves_authoritative_rows` | no lost authoritative state (rows survive), no duplicate side effects (idempotent redelivery), zero broker exposure on a failed write (write-before-send), single trade on resubmission |
| 3 | FalkorDB outage | `test_infra_outages.py::TestFalkordbOutage` | retrieval failure contained + recovers; lesson ingest failure never loses the canonical postmortem |
| 4 | MinIO outage | `test_infra_outages.py::TestMinioOutage`, `test_live_infra_restart.py::TestLiveRestarts::test_minio_restart_roundtrip` | review + audit trail survive (authoritative), redelivery idempotent |
| 5 | LLM timeout | `test_infra_outages.py::TestLlmBoundaryFailures::test_llm_timeout_is_contained_and_the_cycle_recovers` | contained (`TradingAgentsTimeoutError` audited), account untouched, cycle recovers |
| 6 | TradingAgents crash | `test_infra_outages.py::TestLlmBoundaryFailures::test_tradingagents_crash_never_reaches_the_venue_and_recovers` | no proposal/order/account change while down, pipeline resumes when healthy |
| 7 | worker crash | `test_process_crash.py::TestWorkerCrash` | redelivery exactly-once: crash-before-ACK never duplicates work; crash-mid-stage never duplicates side effects (persisted guard) |
| 8 | API crash | `test_process_crash.py::TestApiCrash` | stateless restart, `/readyz` 503 while a dependency is down, liveness independent, identical contract catalog |
| 9 | MT4 disconnect | `test_process_crash.py::TestMt4Disconnect` | dead-man switch engages (`HEARTBEAT_LOST`, CRITICAL alert), new entries blocked, broker positions untouched, heartbeat clears the state |
| 10 | network partition | `test_network_partition.py` (existing) | `SAFE_MODE` (`BROKER_UNREACHABLE`), entries blocked, monitoring/reconciliation allowed, clean exit on recovery |
| 11 | duplicate broker message | `test_broker_event_chaos.py::TestBrokerEventStreamIntegrity::test_duplicate_broker_fill_is_counted_exactly_once`, `TestNoDuplicateFillFingerprint` | fingerprint dedupe: exactly one fill/position, no safe mode |
| 12 | out-of-order broker message | `test_broker_event_chaos.py::TestBrokerEventStreamIntegrity::test_out_of_order_events_resolve_to_correct_state` | correct cumulative state, stale reject after fill is a no-op, no divergence |
| 13 | partial fills | `test_broker_event_chaos.py::TestWireLevelPartialFills` | clean completion (exact quantity, one position, no safe mode); crash after partial → MATERIAL quantity divergence → `SAFE_MODE` blocks entries, nothing adopted or auto-closed |
| 14 | core crash after order submission | `test_restart_recovery.py::test_crash_after_submit_broker_never_saw_is_closed_explainably` (existing) | explainable closure, no lost state |
| 15 | core crash before broker ACK | `test_restart_recovery.py::test_crash_before_ack_is_healed_from_broker_position` (existing) | healed to `FILLED` from the broker position at startup reconciliation |
| 16 | unexpected manual broker trade | `test_network_partition.py::test_unexpected_manual_broker_position_enters_safe_mode` (existing) | MATERIAL divergence → `SAFE_MODE` + CRITICAL alert, position never adopted |

## Validation properties (DoD)

- **no duplicate orders** — fingerprint dedupe, intent idempotency, exactly-once
  redelivery (worker/store guards), broker idempotency ledger;
- **no lost authoritative state** — write-before-send, persisted SUBMITTED,
  PostgreSQL rows surviving restart, canonical reviews surviving sink outages;
- **risk remains enforced** — `SAFE_MODE` blocks `NEW_ENTRY`, emergency
  dead-man blocks entries, outbound orders require persisted state first;
- **reconciliation restores consistency** — startup reconciliation heals
  ACK/fill/position gaps and exits safe mode on a clean run;
- **safe mode activates when required** — broker unreachable, material
  divergence (manual trades, quantity mismatch), overfill.

## Deterministic construction rules

- Faults use the production classes' own retry/recovery paths (e.g. the real
  `RedisStreamBus`, `Stage.handle`/`StageWorker`, `ExecutionService.submit`
  + `startup_reconciliation`) — never re-implemented mimics.
- Wire scenarios run against the MT4 emulator over ZeroMQ loopback (no
  MetaTrader); state scenarios use the deterministic fakes from
  `execution_helpers`/`worker_helpers`.
- Recoveries are scripted: heal the fault, advance the virtual clock, then
  assert the invariant (exactly-once, consistency, safe-mode exit).
- Docker restarts are strictly opt-in (`OT_CHAOS_LIVE=1`).
