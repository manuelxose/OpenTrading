---
name: walk-forward-validation
description: "Validate walk-forward and purged/embargoed CV for time-series ML. Use when training or evaluating models on temporal data."
---

# Walk-Forward Validation

## Purpose
Prevent time-series leakage in model evaluation: train/validate/forward/roll with purging
and embargo (architecture §19).

## Trigger conditions
Model training, CV setup, promotion evidence, Qlib experiment design.

## Inputs
Split configuration, event/overlap parameters, dataset.

## Outputs
Split audit with leakage findings.

## Related agents
`quant-research` (owner), `market-data`.

## Procedure
1. Confirm chronological splits only — no random shuffling across time.
2. Confirm purge gap and embargo after training windows (label overlap).
3. Confirm no future data in any fold.
4. Confirm rolling forward windows cover the full evaluation period.
5. Record split config with the experiment for reproducibility.
