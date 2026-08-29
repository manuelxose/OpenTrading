# Phase 5 — Deterministic Risk & Policy Engine (implementation record)

Status: **implemented** (2026-08-26). Scope: `engines/risk/`,
`core/schemas/risk.py`, RiskDecision RESIZE (ADR-0018), `tests/risk/`.

## What it is

The single most important component (architecture §7, INV-4, ADR-0015,
ADR-0018). 100% own deterministic code — **no LLM, no agent, no prompt-based
decision**. `TradeProposal → Policy checks → Risk sizing → RiskDecision`.

## Inputs

| Contract | File | Content |
|---|---|---|
| `TradeProposal` | `core/schemas/trading.py` | advisory quantity/stop (INV-1) |
| `AccountState` | `core/schemas/risk.py` | equity, free margin, PnL, streak, broker/heartbeat/safe-mode |
| `PortfolioState` | `core/schemas/risk.py` | positions, pending orders, exposure aggregates |
| `MarketSnapshot` | `core/schemas/market.py` | bid/ask, `source_timestamp` freshness |
| `StrategyConfiguration` | `core/schemas/risk.py` | enabled state, instrument restrictions |
| `RiskPolicy` | `core/schemas/risk.py` | versioned limits (no implicit defaults) |
| `Instrument` | `core/schemas/market.py` | lot rules, contract size, asset class |

## Controls

Hard checks (fail-closed → REJECT), canonical order:

1. `STRATEGY_INACTIVE` — disabled/retired/research state, id/version mismatch
2. `SYMBOL_NOT_WHITELISTED` — policy whitelist, strategy instruments, instrument active
3. `STALE_QUOTES` — missing snapshot or `source_timestamp` older than max age
4. `BROKER_DISCONNECTED` / 5. `HEARTBEAT_LOST` / 6. `SAFE_MODE_ACTIVE`
7. `TRADING_HOURS_RESTRICTED` — weekdays + intraday/overnight UTC session
8. `MAX_DAILY_LOSS_REACHED` / 9. `MAX_DRAWDOWN_REACHED`
10. `LOSS_SEQUENCE_COOLDOWN` — consecutive losses + cooldown window
11. `MAX_POSITIONS_REACHED` / 12. `MAX_ORDERS_REACHED`
13. `SPREAD_TOO_HIGH` / 14. `SLIPPAGE_CAP_EXCEEDED` (MARKET orders, worst side)
15. `INVALID_STOP_DISTANCE` — missing, wrong side, closer than minimum

Soft limits (resize the quantity → RESIZE):

- `RISK_LIMIT_EXCEEDED` — effective budget = min(global, strategy budget)
- `CONCENTRATION_LIMIT_EXCEEDED` — instrument / asset class / currency (net)
- `EXPOSURE_LIMIT_EXCEEDED` — total notional
- `LEVERAGE_LIMIT_EXCEEDED` — total notional / equity
- `INSUFFICIENT_MARGIN` — notional × asset-class margin rate ≤ free margin
- `SIZE_ABOVE_MAXIMUM` — effective max = min(policy max, instrument max)
- `LOT_STEP_INVALID` — floor to the instrument lot step
- `SIZE_BELOW_MINIMUM` — cannot resize ≥ minimum → REJECT

## Sizing math (deterministic, exact)

```
entry            = limit_price or mid
stop_distance    = |entry − stop|            (validated ≥ min_stop_distance)
notional/lot     = contract_size × entry
risk/lot         = contract_size × stop_distance
budget           = min(max_risk_per_trade, strategy_budget[strategy_id])
cap(limit)       = remaining headroom of that limit / notional-per-lot
target           = min(proposal.quantity, all caps, effective max)
final            = floor(target / lot_step) × lot_step
exact gate       = walk final down one lot step while any soft limit fails
```

The exact gate re-checks every soft limit with exact Decimal multiplication —
a one-ulp rounding of a derived cap can never let a size through.
`approved_risk = final × risk/lot`; `approved_stop` = the validated proposal
stop (the engine re-derives risk from it, never from an LLM).

## Decision assembly

- hard violations → `REJECT` (all violated codes, canonical order)
- exact gate below minimum → `REJECT` (binding codes + `SIZE_BELOW_MINIMUM`)
- final == proposal quantity → `APPROVE`
- otherwise → `RESIZE` (binding codes, canonical order)

Determinism: the engine is a pure function of its inputs; `inputs_hash`
(SHA-256 over canonical JSON) and the decision id (UUIDv5 over the hash) are
stable across runs.

## Denomination (ADR-0018)

Monetary limits are account-currency; the proposal notional is approximated in
the instrument quote currency until an FX-rate feed exists. `PortfolioExposure`
aggregates are produced by the portfolio engine and re-verified here.

## Tests (`tests/risk/`)

| File | Coverage |
|---|---|
| `test_approve.py` | baseline, LIMIT/SHORT variants, determinism, hash stability |
| `test_reject.py` | every hard check + multi-code ordering |
| `test_resize.py` | every soft cap, normalization, exact approved sizes |
| `test_risk_boundary.py` | exact at-limit / one-epsilon-over boundaries |
| `test_invariants.py` | the five critical invariants + no-bypass grid |
| `test_property_based.py` | Hypothesis: ~1100 arbitrary inputs, exact limits |
| `test_fuzz.py` | 1500 seeded adversarial draws, deterministic seed |

Plus contract tests in `tests/unit/schemas/test_risk_contracts.py` and
`tests/factories.py` factories for every new contract.

## Definition of Done

> No tested path can bypass configured risk limits.

Enforced by construction (the exact gate) and by proof: property-based and
fuzz suites assert, with exact arithmetic, that every approved size satisfies
every soft limit, and that the blocking invariants (daily loss breach, stale
data, disabled strategy) hold unconditionally.
