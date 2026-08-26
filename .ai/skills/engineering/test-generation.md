---
name: test-generation
description: "Write unit, property-based, integration, replay, leakage, and chaos tests. Use when implementing logic, fixing bugs, or proving invariants."
---

# Test Generation

## Purpose
Produce the right test type for the code under change; tests are evidence, not decoration.

## Trigger conditions
Any logic implementation or bugfix; DoD gates.

## Inputs
Code under test + invariants.

## Outputs
Tests + run evidence.

## Related agents
All implementation agents; `verification` uses it adversarially.

## Procedure
1. Map the change to test layers: unit, property-based, integration, replay, leakage,
   backtest, execution, risk, security, chaos (`tests/` layout §27).
2. Risk Engine → property-based invariants (`risk > limit → never approve`).
3. Execution → idempotency (duplicate order_intent_id → one order).
4. Data/memory → leakage tests that fail on future access.
5. Backtest → determinism tests.
6. Keep tests honest: no assertions on mocks alone.
