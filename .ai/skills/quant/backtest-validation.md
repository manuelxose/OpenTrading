---
name: backtest-validation
description: "Validate backtest methodology and determinism. Use when a backtest is created, changed, or its results are cited."
---

# Backtest Validation

## Purpose
Ensure backtests include realistic costs, avoid leakage, and are deterministic
(same input → same output, INV-2/INV-3).

## Trigger conditions
Backtest code, engine changes, result claims, StrategyCandidate evidence.

## Inputs
Backtest config, dataset hash, code SHA, results.

## Outputs
Validity verdict + missing-cost/leakage/determinism findings.

## Related agents
`quant-research` and `trading-backtest` (owners), `verification`.

## Procedure
1. Confirm fees, spread, slippage, swaps, liquidity constraints are modeled.
2. Confirm point-in-time data and no future leakage (pair with point-in-time-validation).
3. Run twice → identical results (deterministic replay).
4. Confirm out-of-sample data was never used in development.
5. Require metric set from §20 with costs.
