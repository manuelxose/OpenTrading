---
name: experiment-reproducibility
description: "Ensure research experiments can be re-run identically. Use when experiments are created, claimed, or used as promotion evidence."
---

# Experiment Reproducibility

## Purpose
Every experiment (including failed ones) is recorded and re-runnable
(architecture §4, §19 multiple-testing protection).

## Trigger conditions
Experiment creation, results claims, StrategyCandidate evidence, MLflow wiring.

## Inputs
Experiment code/config.

## Outputs
Reproducibility checklist verdict.

## Related agents
`quant-research` (owner), `verification` (audits claims).

## Procedure
1. Record: dataset hash, code SHA, seeds, config version, env (runtime 3.11/3.12).
2. Register in MLflow; failed experiments are recorded too.
3. Confirm no hidden nondeterminism (RNG, parallelism, time-dependent logic).
4. Re-run from scratch and diff results.
5. Promotion evidence must cite the exact experiment IDs (§10 of roadmap, Phase 10 DoD).
