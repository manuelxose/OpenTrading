---
name: model-evaluation
description: "Evaluate ML models with temporal validation, calibration, and drift checks. Use when training, comparing, or promoting models."
---

# Model Evaluation

## Purpose
Validate model quality beyond backtest PnL: prediction calibration, drift, robustness.

## Trigger conditions
Model training, model comparison, promotion evidence.

## Inputs
Model artifacts, validation config, feature/dataset hashes.

## Outputs
Metrics + drift/calibration report with verdict.

## Related agents
`quant-research` (owner), `market-data`.

## Procedure
1. Temporal validation only (walk-forward/purged/embargo).
2. Report calibration of predictions (not just accuracy/IC).
3. Monitor feature drift, prediction drift, calibration drift (§20).
4. Sensitivity/parameter perturbation tests (§19).
5. Regime testing (bull/bear/sideways/vol/crisis).
6. Multiple-testing ledger must include this experiment.
