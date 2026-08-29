# engines/promotion — Strategy promotion pipeline (Phase 10)

Candidate → deterministic validation receipt → PAPER → shadow → live-gated (INV-8).
`StrategyValidationFactory` requires basic and cost-aware backtests, OOS, walk-forward,
purged/embargo validation, Monte Carlo, perturbation, regime, sensitivity, and
multiple-testing stages. Quant models also require IC/RankIC, decay, calibration, and
drift diagnostics. Each stage produces an `ExperimentRun`, including failures.

PAPER approvals require a Validation Factory receipt; a high Sharpe alone is never sufficient.
No LLM may promote.
