# mt4/Include — shared MQL4 includes (Phase 6)

Implemented:

- `QuantBridgeProtocol.mqh` — the MQL4 port of the wire protocol:
  - protocol constants (`PROTOCOL_VERSION = "1.0"`, message-type names, error
    codes) mirroring `adapters/mt4/protocol.py` + `errors.py`;
  - flat-JSON parse/build helpers (raw-segment capture keeps the canonical
    checksum byte-exact);
  - SHA-256 canonical checksum verification (`CryptEncode`);
  - the validation gate (expiration → duplicates by
    `(order_intent_id, message_type)` → per-strategy sequence) as pure MQL4
    functions ported from `adapters/mt4/guards.py`, plus the idempotency
    ledger (`IntentLedger`) and sequence tracker (`SequenceTracker`);
  - deterministic UUIDv5 for reply/event `message_id` derivation (SHA-1 via
    `CryptEncode`, same derivation as Python `uuid.uuid5`).
- `QuantBridgeZmq.mqh` — thin ZeroMQ transport wrapper (REP/PUSH/PUB). The
  real sockets live behind `QUANT_BRIDGE_ZMQ` (requires the mql-zmq binding);
  without it the EA compiles and logs traffic instead of sending it.

Install: copy both `.mqh` files into the terminal's `MQL4\Include` directory
(the EA includes them as `<QuantBridgeProtocol.mqh>` / `<QuantBridgeZmq.mqh>`).
