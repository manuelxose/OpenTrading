"""Supervisor configuration: instruments, risk policy, strategy snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal

from core.config.settings import Settings, get_settings
from core.domain.enums import AssetClass, StrategyState
from core.schemas import Instrument, Provenance, RiskPolicy, StrategyConfiguration

from apps.live_supervisor.signals import ScalpParams

__all__ = [
    "DEFAULT_STRATEGY_ID",
    "DEFAULT_STRATEGY_VERSION",
    "LiveSupervisorConfig",
    "build_instrument",
    "build_live_policy",
    "build_strategy_configuration",
]

DEFAULT_STRATEGY_ID = "baseline-momentum-live-001"
DEFAULT_STRATEGY_VERSION = "1.0.0"
POLICY_ID = "live-auto-risk-policy"
POLICY_VERSION = "1.0.0"

#: Live instrument specifications (IC Markets MT4 semantics).
#: ``contract_size`` = base units per 1.0 lot (crypto CFD: 1 lot = 1 coin).
_LIVE_INSTRUMENTS: dict[str, dict[str, object]] = {
    "BTCUSD": {
        "base_currency": "BTC",
        "quote_currency": "USD",
        "tick_size": Decimal("0.01"),
        "price_precision": 2,
        "contract_size": Decimal("1"),
        "asset_class": AssetClass.CRYPTO,
    },
    "ETHUSD": {
        "base_currency": "ETH",
        "quote_currency": "USD",
        "tick_size": Decimal("0.01"),
        "price_precision": 2,
        "contract_size": Decimal("1"),
        "asset_class": AssetClass.CRYPTO,
    },
}

#: MT4 lot constraints (IC Markets crypto CFD).
_LOT_STEP = Decimal("0.01")
_MIN_LOT = Decimal("0.01")
_MAX_LOT = Decimal("100")


@dataclass(frozen=True, slots=True)
class LiveSupervisorConfig:
    """Frozen runtime configuration derived from Settings (OT_* env)."""

    strategy_id: str
    strategy_version: str
    instruments: tuple[str, ...]
    cycle_interval_seconds: int
    position_equity_pct: Decimal
    stop_atr_ratio: Decimal
    take_atr_ratio: Decimal
    max_open_positions: int
    max_spread_points: Decimal
    risk_per_trade: Decimal
    min_strength: Decimal
    persist_bars: bool
    signal_params: ScalpParams

    @property
    def warmup_bars(self) -> int:
        return self.signal_params.warmup_bars

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> LiveSupervisorConfig:
        settings = settings or get_settings()
        instrument_ids = tuple(
            i.strip() for i in settings.live_auto_instruments.split(",") if i.strip()
        )
        unknown = [i for i in instrument_ids if i not in _LIVE_INSTRUMENTS]
        if unknown:
            raise ValueError(f"no live instrument spec for {unknown} (add it to config.py)")
        return cls(
            strategy_id=settings.live_auto_strategy_id,
            strategy_version=settings.live_auto_strategy_version,
            instruments=instrument_ids,
            cycle_interval_seconds=settings.live_auto_cycle_interval_seconds,
            position_equity_pct=settings.live_auto_position_equity_pct,
            stop_atr_ratio=settings.live_auto_stop_atr_ratio,
            take_atr_ratio=settings.live_auto_take_atr_ratio,
            max_open_positions=settings.live_auto_max_open_positions,
            max_spread_points=settings.live_auto_max_spread_points,
            risk_per_trade=settings.live_auto_risk_per_trade,
            min_strength=settings.live_auto_min_strength,
            persist_bars=settings.live_auto_persist_bars,
            signal_params=ScalpParams(
                fast_ema=settings.live_auto_fast_ema,
                slow_ema=settings.live_auto_slow_ema,
                atr_period=settings.live_auto_atr_period,
                min_strength=settings.live_auto_min_strength,
            ),
        )


def build_instrument(instrument_id: str, produced_at: datetime) -> Instrument:
    spec = _LIVE_INSTRUMENTS[instrument_id]
    return Instrument(
        instrument_id=instrument_id,
        symbol=instrument_id,
        exchange="ICMARKETS-DEMO",
        asset_class=spec["asset_class"],  # type: ignore[arg-type]
        base_currency=spec["base_currency"],  # type: ignore[arg-type]
        quote_currency=spec["quote_currency"],  # type: ignore[arg-type]
        price_precision=spec["price_precision"],  # type: ignore[arg-type]
        tick_size=spec["tick_size"],  # type: ignore[arg-type]
        lot_size=Decimal("1"),
        lot_step=_LOT_STEP,
        min_lot=_MIN_LOT,
        max_lot=_MAX_LOT,
        contract_size=spec["contract_size"],  # type: ignore[arg-type]
        produced_at=produced_at,
        provenance=Provenance(producer="apps.live_supervisor", produced_at=produced_at),
    )


def build_live_policy(config: LiveSupervisorConfig, produced_at: datetime) -> RiskPolicy:
    """Explicit, versioned live risk policy (every limit set, INV-4)."""
    return RiskPolicy(
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        produced_at=produced_at,
        provenance=Provenance(producer="apps.live_supervisor", produced_at=produced_at),
        max_risk_per_trade=config.risk_per_trade,
        strategy_risk_budgets={config.strategy_id: config.risk_per_trade},
        max_total_exposure=Decimal("3000"),
        max_instrument_exposure=Decimal("2000"),
        max_asset_class_exposure={AssetClass.CRYPTO: Decimal("3000")},
        max_currency_exposure={"USD": Decimal("3000"), "BTC": Decimal("3000"), "ETH": Decimal("3000")},
        max_leverage=Decimal("50"),
        margin_rates={AssetClass.CRYPTO: Decimal("0.01")},
        max_positions=config.max_open_positions,
        max_pending_orders=2,
        max_daily_loss=Decimal("200"),
        max_drawdown_pct=Decimal("0.20"),
        max_consecutive_losses=3,
        cooldown_seconds=300,
        max_spread_relative=Decimal("0.005"),
        max_slippage_relative=Decimal("0.001"),
        min_stop_distance=Decimal("10"),
        market_data_max_age_seconds=10,
        heartbeat_max_age_seconds=6,
        min_position_size=_MIN_LOT,
        max_position_size=Decimal("0.05"),
        instrument_whitelist=frozenset(config.instruments),
        trading_days=frozenset(range(7)),
        session_open_utc=None,
        session_close_utc=None,
    )


def build_strategy_configuration(
    config: LiveSupervisorConfig, produced_at: datetime
) -> StrategyConfiguration:
    return StrategyConfiguration(
        strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        enabled=True,
        state=StrategyState.LIVE_AUTO,
        allowed_instruments=frozenset(config.instruments),
        produced_at=produced_at,
        provenance=Provenance(producer="apps.live_supervisor", produced_at=produced_at),
        as_of=produced_at,
    )


def utc_now_aware(produced_at: datetime) -> datetime:
    if produced_at.tzinfo is None:
        return produced_at.replace(tzinfo=timezone.utc)
    return produced_at
