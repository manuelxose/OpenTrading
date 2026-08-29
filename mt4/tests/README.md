# mt4/tests — MT4 emulator tests (pointer)

The real suite follows the repo convention and lives in
`tests/unit/mt4/`:

- `test_protocol.py` — wire schemas, framing, checksums, fingerprints
- `test_guards.py` — expiration, duplicates, sequence validation
- `test_broker.py` — EA defense-in-depth venue checks + deterministic matching
- `test_transport.py` — ZeroMQ roundtrips + connection health
- `test_lifecycle.py` — the Phase 6 DoD end-to-end over real loopback ZeroMQ

DoD: sending the same `order_intent_id` 100× never generates more than one
trade — `tests/unit/mt4/test_lifecycle.py::test_same_intent_100_times_produces_one_trade`.

Run: `uv run pytest tests/unit/mt4/` (no MetaTrader, no Docker required).
