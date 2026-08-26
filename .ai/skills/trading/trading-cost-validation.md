---
name: trading-cost-validation
description: "Validate that cost models (fees, spread, slippage, swaps, liquidity) are realistic and applied in backtests. Use when cost models or backtest economics change."
---

# Trading Cost Validation

## Purpose
Ensure backtests never understate costs; costs decide strategy viability (architecture
§16, §19).

## Trigger conditions
Fill/slippage models, commission config, backtest economics, signal-fusion alpha claims.

## Inputs
Cost model + backtest config.

## Outputs
Cost realism verdict.

## Related agents
`trading-backtest` (owner), `quant-research`, `risk`.

## Procedure
1. Confirm fees, spread, slippage, swaps applied on every simulated fill.
2. Validate slippage against realistic distributions, not fixed zero.
3. Include liquidity constraints for size.
4. Post-cost metrics only when claiming alpha (§16).
5. Compare Quant-only / LLM-only / fused against a simple baseline, after costs.
