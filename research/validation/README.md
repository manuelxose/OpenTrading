# research/validation — validation, robustness and anti-overfitting tooling

Implements mandate §33–§44 for `XAU_RPB`. See
[`docs/strategy/VALIDATION_METHODOLOGY.md`](../../docs/strategy/VALIDATION_METHODOLOGY.md).

| Module | Responsibility |
|---|---|
| `metrics.py` | The §42 metric set; long/short, yearly and group attribution |
| `gates.py` | §43 acceptance gates and §44 automatic rejection conditions |
| `splits.py` | Chronological partitions, walk-forward windows, `OosLedger` |
| `sweeps.py` | Parameter sweeps, plateau summaries, cost stress, walk-forward |
| `monte_carlo.py` | Trade-sequence and block bootstrap |
| `overfitting.py` | PBO via CSCV, Deflated Sharpe Ratio, `TrialLedger` |
| `cli.py` | Pipeline entry point |

## Commands

```bash
uv run python -m research.validation.cli data-quality  --data <csv>
uv run python -m research.validation.cli baseline      --data <csv>
uv run python -m research.validation.cli sensitivity   --data <csv>
uv run python -m research.validation.cli walk-forward  --data <csv>
uv run python -m research.validation.cli monte-carlo   --data <csv>
uv run python -m research.validation.cli cost-stress   --data <csv>
uv run python -m research.validation.cli full          --data <csv>
```

Every command requires real market data. **None will fabricate a dataset**: a
report built on invented bars is worse than no report. `full` ends with the frozen
gates and exits non-zero on `REJECTED`.

## Principles encoded here

- Gates were written down **before** any result was seen, and are pinned by tests
  so relaxing one is a visible diff.
- A gate with no input is `NOT_EVALUABLE` — never a silent pass.
- Sweeps look for **plateaus, not peaks**.
- Every trial is recorded, including the losers; the count feeds the Deflated
  Sharpe Ratio.
- Cost stress **re-executes** the strategy rather than rescaling P&L.
