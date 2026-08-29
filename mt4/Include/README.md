# mt4/Include — shared MQL4 includes (Phase 6)

`QuantBridgeProtocol.mqh` will hold the MQL4 port of the wire protocol:

- protocol constants (`PROTOCOL_VERSION = "1.0"`, message-type names, error
  codes) mirroring `adapters/mt4/protocol.py` + `errors.py`;
- JSON parse/build helpers (flat object access only — the spec is flat by
  design, see `mt4/protocol/README.md`);
- optional SHA-256 checksum verification;
- the validation gate (expiry → duplicates by `(order_intent_id, message_type)`
  → per-strategy sequence) as pure MQL4 functions ported from
  `adapters/mt4/guards.py`.

Not yet implemented: the EA comes after the protocol + emulator (ADR-0020).
