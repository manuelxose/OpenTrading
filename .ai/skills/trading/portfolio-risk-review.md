---
name: portfolio-risk-review
description: "Review portfolio and per-trade risk logic against policy. Use for sizing, exposure, limits, drawdown controls, or kill switch changes."
---

# Portfolio Risk Review

## Purpose
Guarantee the deterministic Risk Engine's controls are complete and impossible to bypass
(architecture §7, INV-4).

## Trigger conditions
Any change to sizing, limits, exposure, margin, correlation clusters, kill switches.

## Inputs
Diff + risk policy version.

## Outputs
Control coverage audit + bypass findings.

## Related agents
`risk` (owner), `verification`, `security` (execution paths).

## Procedure
1. Enumerate controls (§7): per-trade risk, exposures (instrument/asset/currency/cluster),
   leverage, simultaneous orders/positions, daily loss, drawdown, spread/slippage caps,
   stops, lot step, margin, quote freshness, turnover, cooldown, hours, event
   restrictions, strategy/symbol enablement, broker/heartbeat/reconciliation gates.
2. Confirm APPROVE carries approved_quantity/stop/policy_version; REJECT carries
   reason_codes (INV-4).
3. Confirm no LLM input and no bypass path.
4. Property-based tests: `risk > limit → never approve`; lot ≤ configured max.
5. Kill-switch and dead-man behaviors intact (INV-7).
