# mt4/Experts — QuantBridgeEA.mq4 (Phase 6, next step)

`QuantBridgeEA.mq4` is the execution-only bridge (ADR-0003, ADR-0016, INV-5):

    Receive command → Validate command → Broker validation → Send order → Return event

It will be a **mechanical MQL4 port** of the Python emulator
(`adapters/mt4/emulator.py` + `broker.py`): same channels (REP / PUSH / PUB),
same validation order, same error codes, same idempotency/sequence semantics —
per the normative spec in `mt4/protocol/README.md`.

Not yet implemented by design: the protocol and emulator were built first so
the Core's lifecycle tests define the EA's behavior (ADR-0020). See
`mt4/README.md` for status.
