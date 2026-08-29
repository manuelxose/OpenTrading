"""The BACKTEST runner: Nautilus ``BacktestEngine`` + virtual clock + domain router.

One facade method turns (dataset, config, domain strategy) into a reproducible
``BacktestRunResult`` (ADR-0007):

- historical market replay via ``engine.add_data`` (bars + synthesized quotes);
- Nautilus ``TestClock`` (the virtual clock) advances with the data stream;
- realistic commissions (notional bps, floored), configurable spread (quote
  synthesis) and slippage (simulated order book), order rejection simulation;
- position accounting mirrored into domain objects by ``PositionLedger``;
- deterministic: no unseeded randomness, ``use_random_ids=False``, seeded fill
  model; two identical runs produce identical outputs (DoD).
"""

from __future__ import annotations

import subprocess
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from core.domain.enums import AssetClass
from core.schemas import Instrument
from core.schemas.base import Provenance
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue
from nautilus_trader.model.objects import Currency, Money

from adapters.nautilus.config import BacktestConfig
from adapters.nautilus.dataset import Dataset, build_dataset
from adapters.nautilus.ledger import PositionLedger
from adapters.nautilus.mapping import instrument_to_nautilus
from adapters.nautilus.metrics import EquityPoint, compute_metrics
from adapters.nautilus.models import ConfigurableSlippageFillModel, NotionalCommissionFeeModel
from adapters.nautilus.results import BacktestRunResult, compute_output_hash, input_fingerprint
from adapters.nautilus.router import NautilusRouterStrategy
from adapters.nautilus.strategy import BaselineSmaStrategy, DomainStrategy

__all__ = ["NautilusBacktestRunner", "code_sha", "eurusd_instrument"]

_ADAPTER_VERSION = "1.0.0"
_INSTRUMENT_FIXED_TS = datetime(2026, 1, 1, tzinfo=UTC)


def code_sha() -> str:
    """Git HEAD SHA of the repository, or the adapter version outside a repo.

    The code SHA is part of the DoD input fingerprint: dataset + config + code SHA
    reproduce the same backtest result.
    """
    try:
        cwd = Path(__file__).resolve().parents[2]
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        sha = out.stdout.strip()
        if sha:
            return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return _ADAPTER_VERSION


def eurusd_instrument() -> Instrument:
    """Canonical EURUSD domain instrument (mirrors ``tests.factories.make_instrument``)."""
    return Instrument(
        instrument_id="EURUSD",
        symbol="EURUSD",
        exchange="FX",
        asset_class=AssetClass.FX,
        base_currency="EUR",
        quote_currency="USD",
        price_precision=5,
        tick_size=Decimal("0.00001"),
        lot_size=Decimal("100000"),
        lot_step=Decimal("0.01"),
        min_lot=Decimal("0.01"),
        max_lot=Decimal("100"),
        produced_at=_INSTRUMENT_FIXED_TS,
        provenance=Provenance(producer="adapters.nautilus", produced_at=_INSTRUMENT_FIXED_TS),
    )


class NautilusBacktestRunner:
    """Runs one BACKTEST with the Nautilus simulated venue (virtual clock)."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config

    def run(self, domain_strategy: DomainStrategy | None = None) -> BacktestRunResult:
        config = self._config
        venue = Venue(config.venue_name)
        nautilus_instrument = instrument_to_nautilus(config.instrument, venue)
        dataset = build_dataset(config.dataset, config.instrument, config.spread, venue)
        strategy = domain_strategy or BaselineSmaStrategy(config.baseline)
        base_currency = config.instrument.base_currency
        if base_currency is None:
            raise ValueError("FX instrument requires base_currency")

        ledger = PositionLedger(
            config.instrument,
            {
                config.account_currency: config.starting_balance,
                base_currency: config.starting_balance,
            },
            config.account_currency,
            fallback_mark=config.dataset.initial_mid,
        )

        fill_model = ConfigurableSlippageFillModel(
            fixed_ticks=config.slippage.fixed_ticks,
            random_min_ticks=config.slippage.random_min_ticks,
            random_max_ticks=config.slippage.random_max_ticks,
            seed=config.seed,
            prob_fill_on_limit=config.prob_fill_on_limit,
            prob_fill_on_stop=config.prob_fill_on_stop,
        )
        fee_model = NotionalCommissionFeeModel(
            rate_bps=config.commission.rate_bps, min_amount=config.commission.min_amount
        )

        engine = BacktestEngine(
            BacktestEngineConfig(
                trader_id=TraderId(config.trader_id),
                logging=LoggingConfig(log_level="ERROR"),
            )
        )
        venue_balances: dict[str, Decimal] | None = None
        try:
            engine.add_venue(
                venue=venue,
                oms_type=OmsType.NETTING,
                account_type=AccountType.CASH,
                starting_balances=[
                    Money(config.starting_balance, Currency.from_str(config.account_currency)),
                    Money(
                        config.starting_balance,
                        Currency.from_str(base_currency),
                    ),
                ],
                base_currency=None,
                fill_model=fill_model,
                fee_model=fee_model,
                use_random_ids=False,
                reject_stop_orders=True,
                # Bars are signal data only; fills must come from the synthesized
                # quotes through the (slippage-aware) simulated order book.
                bar_execution=False,
            )
            engine.add_instrument(nautilus_instrument)
            engine.add_data(dataset.bars)
            engine.add_data(dataset.quotes)
            router = NautilusRouterStrategy(
                config, strategy, ledger, dataset, nautilus_instrument, fill_model
            )
            engine.add_strategy(router)
            engine.run(start=dataset.start_time, end=dataset.end_time)
            venue_balances = self._venue_balances(engine, venue)
        finally:
            with suppress(Exception):  # dispose is best-effort after a failure
                engine.dispose()

        return self._build_result(dataset, ledger, router, venue_balances, config)

    @staticmethod
    def _venue_balances(engine: BacktestEngine, venue: Venue) -> dict[str, Decimal]:
        """Authoritative balances as tracked by the Nautilus venue (for cross-checks)."""
        account = engine.portfolio.account(venue)
        return {
            str(currency): money.as_decimal()
            for currency, money in account.balances_total().items()
        }

    def _build_result(
        self,
        dataset: Dataset,
        ledger: PositionLedger,
        router: NautilusRouterStrategy,
        venue_balances: dict[str, Decimal] | None,
        config: BacktestConfig,
    ) -> BacktestRunResult:
        equity_curve = [EquityPoint(ts=ts, equity=equity) for ts, equity in router.equity_points]
        metrics = compute_metrics(
            ledger.outcomes,
            equity_curve,
            bars_per_year=365 * 24 * 3600 / config.dataset.interval_seconds,
        )
        final_balances = ledger.balances()
        dataset_hash = dataset.dataset_hash
        config_hash = config.config_hash()
        sha = code_sha()
        return BacktestRunResult(
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            code_sha=sha,
            input_hash=input_fingerprint(dataset_hash, config_hash, sha),
            output_hash=compute_output_hash(
                router.execution_reports,
                ledger.outcomes,
                ledger.open_positions(),
                equity_curve,
                metrics,
                final_balances,
            ),
            venue=config.venue_name,
            instrument_id=config.instrument.instrument_id,
            start_time=dataset.start_time,
            end_time=dataset.end_time,
            execution_reports=router.execution_reports,
            trade_outcomes=ledger.outcomes,
            final_positions=ledger.open_positions(),
            equity_curve=equity_curve,
            final_balances=final_balances,
            venue_balances=venue_balances,
            metrics=metrics,
        )
