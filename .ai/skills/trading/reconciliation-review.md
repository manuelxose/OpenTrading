---
name: reconciliation-review
description: "Review broker-state reconciliation between Core DB and MT4. Use when reconciliation, restart recovery, or SAFE_MODE logic changes."
---

# Reconciliation Review

## Purpose
Guarantee DB state and broker state converge or the system enters SAFE_MODE
(architecture §9, INV-6).

## Trigger conditions
Reconciliation code, restart logic, broker event handling.

## Inputs
Diff + state model.

## Outputs
Divergence-handling audit.

## Related agents
`execution-mt4` (owner), `risk`, `backend-platform`.

## Procedure
1. Verify restart path: load DB state + broker state → reconcile → resolve.
2. Verify divergence → SAFE_MODE blocks new entries.
3. Verify duplicate/out-of-order broker events are handled (chaos tests).
4. Verify partial fills and broker-side closes are detected.
5. Run chaos scenarios: crash before ACK, crash after submit, duplicate events.
