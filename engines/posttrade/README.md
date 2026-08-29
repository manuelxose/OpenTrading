# engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023)

Closed-and-reconciled trade → deterministic postmortem → four sinks
(architecture §17). Pure functions, no IO, no clocks, no risk-limit writes.

## Layout

| Module | Responsibility |
|---|---|
| `metrics.py` | `compute_trade_metrics`: PnL, fees, slippage, R multiple, alpha, MAE/MFE (from the observed price path), holding time, entry/exit efficiency, per-producer Brier calibration error, prediction error, regime |
| `analysis.py` | `analyze`: independent quality evaluations (quant / llm / fused / risk / execution), expected-vs-actual, deterministic lessons, verdict + thesis summary |
| `persistence.py` | `posttrade_reviews` table + `PostTradeStore` (InMemory + Postgres, idempotent by review_id) |
| `artifacts.py` | immutable MinIO audit artifact (review + metrics + context + path), `posttrade-artifacts` bucket |
| `notes.py` | deterministic Obsidian note rendering + `50_Postmortems/...` path |

## Metric definitions

- `pnl_gross` / `pnl_net` — realized PnL before/after fees (account currency).
- `r_multiple` — net PnL over the Risk-Engine-approved risk amount (None when unknown).
- `alpha_pct` — actual − expected return (plan-relative), or actual − benchmark when supplied.
- `mae_pct` / `mfe_pct` — max adverse/favorable excursion vs entry from the observed path (None when no path — never fabricated).
- `entry_efficiency` = (exit − entry)/(best − entry); `exit_efficiency` = (exit − worst)/(best − worst) clamped to [0, 1].
- `signal_calibration_error` — per-producer Brier error (confidence − hit)².
- `prediction_error_pct` — |actual − predicted| return.

## Invariants

- INV-1: the engine never imports the risk engine or `RiskPolicy`; it only reads the entry `RiskDecision`. Enforced by `tests/unit/posttrade/test_posttrade_risk_invariant.py`.
- INV-6: the stage that calls this engine runs only for terminal (CLOSED/RECONCILED/REVIEWED) orders.
- INV-10: PostgreSQL = typed metrics; MinIO = heavy artifact; Graphiti = semantic lesson; Obsidian = human note.
