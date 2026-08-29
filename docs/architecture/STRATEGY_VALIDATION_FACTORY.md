# Strategy Validation Factory

`StrategyValidationFactory` is the deterministic promotion gate between
`ROBUSTNESS_OK` and PAPER. It receives an adapter-owned runner and a durable
experiment recorder; it never sends orders, changes risk policy, or changes an operating mode.

## Required stages

Every candidate runs: basic backtest; transaction costs; spread; slippage; swap/financing;
out-of-sample; walk-forward; purged validation; embargo (unless the deterministic policy
marks it inapplicable); Monte Carlo; parameter perturbation; regime tests; sensitivity;
and multiple-testing controls. Quant-model candidates additionally run factor diagnostics.

The basic backtest must report CAGR, Sharpe, Sortino, Calmar, maximum drawdown, profit
factor, expectancy, turnover, tail loss, stability, and regime dependence. Quant diagnostics
must report IC, RankIC, factor decay, calibration, and drift sensitivity.

The deterministic policy rejects a candidate that loses excessive CAGR under costs,
spread, slippage, or financing; whose perturbed configurations fail to retain sufficient
performance; whose Monte Carlo pass rate is inadequate; or whose adjusted p-value/multiple-
testing ledger fails policy. A good Sharpe alone is never a pass.

## Evidence and PAPER eligibility

One canonical `ExperimentRun` is created and sent to the recorder for every attempted stage,
including runner exceptions and policy failures. `ValidationReport` contains the complete
required-stage set and a receipt ID. `PaperEligibility.assert_eligible` refuses reports that
are incomplete, belong to another candidate, contain failures, or are not at `ROBUSTNESS_OK`.
`PromotionDecision` also requires a validation receipt for an approved PAPER transition.

All validation configurations require `as_of`, a random seed, and a config hash. Runners are
therefore responsible for point-in-time data, purged/embargo semantics, and execution-cost
simulation at their boundary.
