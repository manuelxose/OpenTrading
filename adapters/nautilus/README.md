# adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007)

NautilusTrader is the event-driven simulation engine. OpenTrading domain models
**never move into Nautilus**; `mapping.py` is the only translation point.

```
Signal → Risk → OrderIntent            (canonical, INV-2)
                  ├── BACKTEST → this adapter (Nautilus simulated venue, virtual clock)
                  ├── PAPER    → this adapter (same router, live data)
                  └── LIVE     → MT4 execution adapter
```

## Layout

| Module       | Responsibility                                                                 |
|--------------|--------------------------------------------------------------------------------|
| `config.py`  | `BacktestConfig` — everything needed to reproduce a run; stable `config_hash()` |
| `dataset.py` | Deterministic datasets: seeded synthetic OHLCV or parquet replay → bars + quotes |
| `mapping.py` | `Instrument`→`CurrencyPair`, `OrderIntent`→native orders, events→`ExecutionReport`/`PositionSnapshot`/`TradeOutcome` |
| `models.py`  | `ConfigurableSlippageFillModel`, `NotionalCommissionFeeModel` (seeded, cost-inclusive) |
| `rejection.py` | Deterministic order rejection simulation (lot rules, price guard, market hours, seeded random) |
| `ledger.py`  | Domain-side position accounting mirror; verified against the venue's own balances |
| `strategy.py` | `DomainStrategy` protocol + `BaselineSmaStrategy` (deterministic, no LLMs) |
| `router.py`  | `NautilusRouterStrategy` — routes `OrderIntent`s into the engine and maps events back |
| `metrics.py` | End-of-run portfolio metrics (cost-inclusive) |
| `engine.py`  | `NautilusBacktestRunner` — one facade call per reproducible run |
| `cli.py`     | Cross-process DoD check: prints `input_hash` / `output_hash` |

## BACKTEST mode on the virtual clock

`NautilusBacktestRunner.run()` builds a `BacktestEngine` whose internal clock is
Nautilus' `TestClock` (the virtual clock); time advances strictly with the
historical data stream. Covered requirements:

- **historical market replay** — bars (+ synthesized bid/ask quotes) injected via `engine.add_data`;
- **realistic commissions** — notional bps per fill, floored, charged in quote currency;
- **configurable spread** — `SpreadConfig.half_spread_ticks` around each bar close;
- **configurable slippage** — deterministic ticks + optional seeded random ticks via a simulated order book;
- **order rejection simulation** — lot rules, price guard, market hours, seeded random rejections, plus engine-native rejections;
- **position accounting** — `PositionLedger` mirrors venue events; balances match the venue exactly (tested);
- **deterministic runs** — no unseeded randomness, `use_random_ids=False`, seeded fill/rejection RNGs;
- **reproducible seeds** — every randomness source derives from `BacktestConfig.seed`;
- **end-of-run portfolio metrics** — `PortfolioMetrics` (cost-inclusive, architecture §20).

## Definition of Done

```bash
uv run python -m adapters.nautilus.cli --seed 42   # print fingerprints
uv run python -m adapters.nautilus.cli --seed 42   # identical output_hash
```

`input_hash = sha256(dataset_hash | config_hash | git HEAD SHA)`,
`output_hash = sha256(all domain outputs)`. Same dataset + config + code SHA →
same output hash, in-process and across processes (enforced by
`tests/backtest/test_determinism.py`).

## Extending to PAPER / LIVE

The canonical `OrderIntent` already crosses the boundary; PAPER swaps the data
source for a live feed and LIVE routes through the MT4 adapter — the mapping and
router stay the same (INV-2: never divergent implementations).
