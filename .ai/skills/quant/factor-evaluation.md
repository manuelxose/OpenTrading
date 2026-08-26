---
name: factor-evaluation
description: "Evaluate a factor's predictive quality (IC/RankIC, stability, decay, turnover). Use when adding factors or judging factor candidates."
---

# Factor Evaluation

## Purpose
Separate real predictive factors from noise using standardized metrics (architecture §20).

## Trigger conditions
New factor, factor changes, RD-Agent factor candidates, decay reports.

## Inputs
Factor implementation, dataset hash, evaluation config.

## Outputs
IC/RankIC, stability, decay, turnover report with verdict.

## Related agents
`quant-research` (owner), `market-data`.

## Procedure
1. Compute IC and RankIC over the evaluation window.
2. Check IC stability across subperiods and regimes.
3. Check factor decay; flag unstable short-half-life factors.
4. Account for turnover costs.
5. Apply multiple-testing discipline for RD-Agent generated factors (§19):
   record ALL experiments including failures.
6. Sensitivity: a factor that only works for one magic parameter value is rejected (§19).
