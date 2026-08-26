---
name: order-lifecycle-review
description: "Review the order state machine end-to-end (CANDIDATE → RECONCILED/CLOSED). Use when order handling, persistence, or transitions change."
---

# Order Lifecycle Review

## Purpose
Guarantee the §9 state machine, idempotency, and auditability of every order.

## Trigger conditions
Order state changes, order persistence, execution reporting, reconciliation logic.

## Inputs
Diff + state machine docs.

## Outputs
Transition audit + idempotency findings.

## Related agents
`execution-mt4` and `trading-backtest` (owners), `risk`.

## Procedure
1. Verify legal states/transitions per §9; no skips or invented states.
2. Verify duplicate `order_intent_id` never yields a second order (dedup + DB uniqueness).
3. Verify every transition is persisted (Postgres truth) with trace_id.
4. Verify restart reconciliation path exists (INV-6).
5. Verify partial fills update state correctly.
