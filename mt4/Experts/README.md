# mt4/Experts — QuantBridgeEA.mq4 (Phase 6)

`QuantBridgeEA.mq4` is the execution-only bridge (ADR-0003, ADR-0016, INV-5):

    Receive command → Validate command → Broker validation → Send order → Return event

Implemented as a **mechanical MQL4 port** of the Python emulator
(`adapters/mt4/emulator.py` + `broker.py`): same channels (REP / PUSH / PUB),
same validation order, same error codes, same idempotency/sequence semantics —
per the normative spec in `mt4/protocol/README.md`.

## Install, compile, attach

1. Copy `Include/*.mqh` into the terminal's `MQL4\Include` and this `.mq4`
   into `MQL4\Experts` (or open the repo folder directly in MetaEditor).
2. Compile in MetaEditor (F7) — clean build: 0 errors, 0 warnings.
3. Drag the EA onto a chart. Before attaching to a **live** account:
   - verify the inputs against the Core settings: `CommandAddr` / `EventsAddr` /
     `QuotesAddr` must match `OT_MT4_COMMAND_ADDR` / `OT_MT4_EVENTS_ADDR` /
     `OT_MT4_QUOTES_ADDR`;
   - set `InputSymbolWhitelist` to exactly the symbols the Core may trade;
   - consider `InputSafeMode=true` until the first reconciliation passes.

## Behavior notes

- Commands are served from `OnTimer` (poll interval `InputPollMilliseconds`);
  heartbeats ride the same timer (dead-man semantics, INV-7).
- Market quotes publish on every tick (`OnTick`) with `topic = symbol`.
- `OrderSend` carries the deterministic MagicNumber
  (`SHA-256(strategy_id)[0:4] & 0x7FFFFFFF`) and a `QB:<hash>` comment.
- The idempotency ledger is in-memory: after an EA restart the Core must
  reconcile (INV-6) before resyncing sequences.
- `STOP_LIMIT` is rejected (`BROKER_ERROR`): `OrderSend` cannot express the
  two-price stop-limit without broker-side support.

## Transport

The ZeroMQ sockets require the mql-zmq binding (dingmaotu/mql-zmq) and
`QUANT_BRIDGE_ZMQ` defined in `Include/QuantBridgeZmq.mqh`. Without it the EA
still compiles and logs traffic instead of sending it.
