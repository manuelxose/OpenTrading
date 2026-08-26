---
name: execution-safety
description: "Review execution paths for safety: idempotency, expiries, heartbeats, defense-in-depth. Use for MT4 bridge, EA, or order transmission changes."
---

# Execution Safety

## Purpose
Ensure the MT4 execution path cannot double-send, over-send, or send stale commands
(architecture §8).

## Trigger conditions
QuantBridgeEA.mq4, ZeroMQ gateway, command protocol, heartbeat changes.

## Inputs
Diff + protocol schema.

## Outputs
Safety findings with severity.

## Related agents
`execution-mt4` (owner), `risk`, `security`.

## Procedure
1. Idempotency: same order_intent_id 100× → exactly one order.
2. Command expiry enforced on both sides.
3. Heartbeat contract defined; dead-man behavior verified (INV-7).
4. EA defense-in-depth checks present (whitelist, lot limits/step, spread, quote
   freshness, market open, stop/freeze levels, MagicNumber).
5. No strategy logic in MQL4 (INV-5).
6. Transport private only (INV-9).
