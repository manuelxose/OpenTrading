# adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020)

Versioned JSON-over-ZeroMQ protocol between the Core and the MT4 execution
bridge (execution-only, INV-5). Build order was deliberate: **protocol and
Python emulator first, EA second** — the emulator defines the behavior
`QuantBridgeEA.mq4` will port.

## Modules

| Module | Purpose |
|---|---|
| `protocol.py` | wire models for all 13 messages, envelope, checksums, content fingerprints, `parse/serialize` (schema validation gate) |
| `errors.py` | `Mt4ErrorCode` vocabulary + `ProtocolErrorDetail` + `Mt4ProtocolError` (one code set for Python and MQL4) |
| `ledger.py` | `IntentLedger` (idempotency keyed by `(order_intent_id, message_type)`) + `SequenceTracker` (strict per-strategy monotonic) |
| `guards.py` | `CommandGate`: expiry → duplicates → sequence, in the frozen order of the spec |
| `broker.py` | `SimulatedBroker` + `QuoteEngine` + `SymbolSpec`/`BrokerConfig`: deterministic venue with the EA defense-in-depth checks (§8/INV-5) |
| `transport.py` | ZeroMQ plumbing, `Mt4Endpoints`, `ConnectionMonitor` (CONNECTED→DEGRADED→DOWN) |
| `client.py` | `Mt4ExecutionClient` — the Core's single door to the bridge (submit/cancel/modify/reconcile, events/quotes, health, sequence resync) |
| `emulator.py` | `Mt4Emulator` — Python stand-in for `QuantBridgeEA.mq4` + broker (REP/PUSH/PUB serve loop, heartbeat, safe-mode) |
| `builders.py` | `OrderIntent` ↔ wire command mapping; fill events → canonical `ExecutionReport` |
| `config.py` | `Mt4Settings` (`OT_MT4_*` env) |
| `cli.py` | `run` (standalone emulator) and `smoke` (in-process lifecycle) |

## Topology

```
Core (REQ) ──submit/cancel/modify/reconcile──▶ (REP) Bridge/Emulator
Core (REQ) ◀──order_ack/order_reject/reconcile── (REP)
Core (PULL) ◀─heartbeat/account/position/partial_fill/fill─ (PUSH)
Core (SUB)  ◀──market_quote (topic=symbol)── (PUB)
```

## Guarantees implemented

idempotency, duplicate detection, sequence validation, command expiration,
schema validation, connection health, structured error codes — plus checksum
integrity and restart resync via `reconciliation_response.last_sequences`.

## Usage

```bash
uv run python -m adapters.mt4.cli run --seed 42   # standalone emulator
uv run python -m adapters.mt4.cli smoke           # in-process lifecycle
uv run pytest tests/unit/mt4/                     # full suite (no MetaTrader)
```

Normative wire spec: `mt4/protocol/README.md`. Decision record: ADR-0020.
