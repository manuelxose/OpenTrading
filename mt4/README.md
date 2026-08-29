# mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5)

`Experts/QuantBridgeEA.mq4` will be a deliberately minimal EA:

    Receive command → Validate command → Broker validation → Send order → Return event

Transport: private ZeroMQ over WireGuard (never internet-exposed; `WebRequest`
rejected per ADR-0003). No strategy intelligence ever migrates into MQL4.

## Status

- ✅ **Protocol v1.0 designed and implemented** — see `mt4/protocol/README.md`
  (normative wire spec) and ADR-0020. Python implementation lives in
  `adapters/mt4/`: wire messages, idempotency/duplicate detection, sequence
  validation, command expiration, schema + checksum validation, connection
  health, structured error codes.
- ✅ **Python MT4 emulator** (`adapters/mt4/emulator.py` + `broker.py`) — the
  bridge + a deterministic simulated venue. The Core executes the full
  lifecycle suite against it with no MetaTrader installed (Phase 6 DoD):
  `tests/unit/mt4/`.
- ⏳ **QuantBridgeEA.mq4** — to be written as a mechanical MQL4 port of the
  emulator's gate and venue checks. Not started (by design: protocol first).

## Layout

| Path | Purpose |
|---|---|
| `protocol/README.md` | normative wire spec for the MQL4 implementer |
| `Include/` | shared MQL4 includes (protocol constants + JSON/checksum helpers) |
| `Experts/QuantBridgeEA.mq4` | the execution-only EA (next step) |
| `tests/` | pointer to the real suite in `tests/unit/mt4/` (repo test convention) |

## Run the emulator / lifecycle

```bash
# Standalone emulator on the default loopback endpoints
uv run python -m adapters.mt4.cli run --seed 42

# In-process lifecycle smoke (submit/ack/fill/cancel/modify/reject/reconcile)
uv run python -m adapters.mt4.cli smoke

# Full DoD suite (no MetaTrader, no Docker required)
uv run pytest tests/unit/mt4/
```

Phase 6 DoD: sending the same `order_intent_id` 100× never generates more than
one trade — proven end-to-end in `tests/unit/mt4/test_lifecycle.py`.

## Setting up a real MT4 terminal locally (Windows)

Installing a real MetaTrader 4 terminal today gets you a terminal ready for
when `QuantBridgeEA.mq4` ships — it does not yet connect to anything here,
since the EA above doesn't exist. To exercise the full Core↔MT4 lifecycle
now, run the emulator (`cli run`/`smoke` above) instead. See
`docs/runbooks/local-development-windows.md` for the Windows/WSL2 setup and
terminal installation steps.
