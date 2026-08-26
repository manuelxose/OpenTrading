---
name: state-machine-review
description: "Review state machines (order lifecycle, strategy promotion, system modes). Use when states, transitions, or their persistence change."
---

# State Machine Review

## Purpose
Guarantee legal transitions, persistence, and recovery for the order state machine (§9),
strategy lifecycle (§18), and operating modes (§6).

## Trigger conditions
Changes to order states, promotion states, mode transitions, reconciliation.

## Inputs
State diagram/diff + persistence layer.

## Outputs
Transition table audit with illegal-transition findings.

## Related agents
`principal-architect` (owner), `trading-backtest`, `risk`, `execution-mt4`.

## Procedure
1. List all legal transitions; check no illegal shortcut exists (e.g. IDEA → LIVE).
2. Check every state survives restart (DB persistence + reconciliation — INV-6).
3. Check divergence handling (SAFE_MODE).
4. Property/enum tests cover transitions.
