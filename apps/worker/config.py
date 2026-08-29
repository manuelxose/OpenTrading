"""Configuration for the autonomous PAPER pipeline (Phase 7).

``PaperPipelineConfig`` is a plain, versionable pydantic document (no clocks,
no IO) describing *what* the pipeline does: watchlist, cadence, producers,
fusion, proposal sizing, risk policy parameters and the Nautilus paper venue.
Runtime objects (``RiskPolicy``, ``Instrument``, ``PaperVenueConfig``) are
built from it through deterministic factory functions, so the same config
reproduces the same behavior.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from adapters.nautilus.paper import PaperVenueConfig
from core.domain.enums import AssetClass, OperatingMode, StrategyState, Timeframe
from core.schemas import Instrument, RiskPolicy, StrategyConfiguration
from core.schemas.base import Provenance
from core.schemas.fusion import INPUT_NAMES
from engines.signal_fusion.config import ComponentWeights, FusionConfig
from pydantic import BaseModel, Field

__all__ = [
    "InstrumentSpec",
    "PaperPipelineConfig",
    "PaperPolicyParams",
    "PostTradeParams",
    "make_instrument",
    "make_paper_policy",
    "make_paper_venue",
    "paper_fusion_config",
]

CONFIG_PRODUCER = "apps.worker.config"


class InstrumentSpec(BaseModel):
    """Static description of one tradable FX instrument."""

    instrument_id: str = Field(pattern=r"^[A-Z0-9._/-]{1,32}$")
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    quote_currency: str = Field(pattern=r"^[A-Z]{3}$")
    tick_size: Decimal = Field(gt=0)
    price_precision: int = Field(default=5, ge=0, le=8)
    lot_size: Decimal = Field(default=Decimal("100000"), gt=0)
    lot_step: Decimal = Field(default=Decimal("1"), gt=0)
    min_lot: Decimal = Field(default=Decimal("1"), gt=0)
    max_lot: Decimal = Field(default=Decimal("100"), gt=0)
    contract_size: Decimal = Field(default=Decimal("100000"), gt=0)
    initial_mid: Decimal = Field(gt=0)


class PaperPolicyParams(BaseModel):
    """Risk policy parameters (all limits explicit, INV-4)."""

    max_risk_per_trade: Decimal = Field(default=Decimal("1000"), gt=0)
    max_total_exposure: Decimal = Field(default=Decimal("500000"), gt=0)
    max_instrument_exposure: Decimal = Field(default=Decimal("200000"), gt=0)
    max_currency_exposure: dict[str, Decimal] = Field(
        default_factory=lambda: {"USD": Decimal("500000")}
    )
    margin_rate_fx: Decimal = Field(default=Decimal("0.02"), gt=0, lt=1)
    max_leverage: Decimal = Field(default=Decimal("50"), gt=0)
    max_positions: int = Field(default=3, ge=1)
    max_pending_orders: int = Field(default=5, ge=1)
    max_daily_loss: Decimal = Field(default=Decimal("1000"), gt=0)
    max_drawdown_pct: Decimal = Field(default=Decimal("0.20"), gt=0, lt=1)
    max_consecutive_losses: int = Field(default=5, ge=1)
    cooldown_seconds: int = Field(default=60, ge=0)
    max_spread_relative: Decimal = Field(default=Decimal("0.005"), ge=0)
    max_slippage_relative: Decimal = Field(default=Decimal("0.002"), ge=0)
    min_stop_distance: Decimal = Field(default=Decimal("0.00001"), gt=0)
    market_data_max_age_seconds: int = Field(default=3600, ge=0)
    heartbeat_max_age_seconds: int = Field(default=60, ge=0)
    min_position_size: Decimal | None = Field(default=None, gt=0)
    max_position_size: Decimal | None = Field(default=None, gt=0)


class ProposalParams(BaseModel):
    """Deterministic proposal shaping (LLMs never size, INV-1)."""

    position_equity_pct: Decimal = Field(default=Decimal("0.02"), gt=0, lt=1)
    stop_atr_ratio: Decimal = Field(default=Decimal("1.5"), gt=0)
    take_atr_ratio: Decimal = Field(default=Decimal("3"), gt=0)
    min_strength: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)


class BusParams(BaseModel):
    """Redis Streams parameters for the unattended worker."""

    stream_key: str = Field(default="opentrading:events", min_length=1)
    group_prefix: str = Field(default="opentrading-workers", min_length=1)
    consumer_name: str = Field(default="worker-1", min_length=1)
    max_deliveries: int = Field(default=5, ge=1)
    block_ms: int = Field(default=2000, ge=0)
    batch_size: int = Field(default=10, ge=1)
    claim_idle_ms: int = Field(default=0, ge=0)
    retry_base_seconds: float = Field(default=1.0, gt=0)
    retry_max_seconds: float = Field(default=30.0, gt=0)


class PostTradeParams(BaseModel):
    """Post-trade learning loop sink configuration (architecture §17).

    The four sinks are independently switchable; the canonical PostgreSQL
    metrics row is always written (DoD backbone). Post-trade analysis never
    writes to risk limits — there is no switch for that.
    """

    vault_path: str = Field(default="vault-trading", min_length=1)
    artifact_bucket: str = Field(default="posttrade-artifacts", min_length=1)
    store_artifacts: bool = True
    write_vault_notes: bool = True
    ingest_lessons: bool = True


class PaperPipelineConfig(BaseModel):
    """Full autonomous PAPER pipeline configuration."""

    name: str = Field(default="paper-pipeline-v1", min_length=1)
    strategy_id: str = Field(default="paper-baseline-001", min_length=1)
    strategy_version: str = Field(default="1.0.0", min_length=1)
    account_id: str = Field(default="paper-account-001", min_length=1)
    account_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    starting_balance: Decimal = Field(default=Decimal("100000"), gt=0)
    operating_mode: OperatingMode = OperatingMode.PAPER
    cycle_interval_seconds: int = Field(default=300, ge=1)
    instruments: dict[str, InstrumentSpec] = Field(min_length=1)
    llm_enabled: bool = True
    llm_required: bool = False  # False: a failed LLM never blocks the cycle
    llm_timeout_seconds: float = Field(default=300.0, gt=0)
    llm_retry_attempts: int = Field(default=2, ge=0)
    llm_provider: str = Field(default="openai", min_length=1)
    quant_model_id: str = Field(default="baseline.momentum.v1", min_length=1)
    quant_model_version: str = Field(default="1.0.0", min_length=1)
    memory_version: str = Field(default="engines.memory.v1", min_length=1)
    memory_query_template: str = Field(default="{instrument} outlook")
    snapshot_source: str = Field(default="repository", pattern=r"^(repository|synthetic)$")
    synthetic_seed: int = 42
    proposal: ProposalParams = Field(default_factory=ProposalParams)
    risk: PaperPolicyParams = Field(default_factory=PaperPolicyParams)
    fusion: FusionConfig | None = None
    venue: PaperVenueConfig = Field(default_factory=PaperVenueConfig)
    bus: BusParams = Field(default_factory=BusParams)
    posttrade: PostTradeParams = Field(default_factory=PostTradeParams)

    @property
    def watchlist(self) -> tuple[str, ...]:
        return tuple(self.instruments)


def make_instrument(spec: InstrumentSpec, produced_at: datetime) -> Instrument:
    """Build the canonical ``Instrument`` for one configured symbol."""
    return Instrument(
        instrument_id=spec.instrument_id,
        symbol=spec.instrument_id,
        exchange="FX",
        asset_class=AssetClass.FX,
        base_currency=spec.base_currency,
        quote_currency=spec.quote_currency,
        price_precision=spec.price_precision,
        tick_size=spec.tick_size,
        lot_size=spec.lot_size,
        lot_step=spec.lot_step,
        min_lot=spec.min_lot,
        max_lot=spec.max_lot,
        contract_size=spec.contract_size,
        produced_at=produced_at,
        provenance=Provenance(producer=CONFIG_PRODUCER, produced_at=produced_at),
    )


def make_paper_policy(
    params: PaperPolicyParams,
    produced_at: datetime,
    currencies: set[str] | None = None,
) -> RiskPolicy:
    """Build the versioned ``RiskPolicy`` consumed by the Risk Engine.

    Every configured base/quote currency gets an explicit exposure limit
    (default: the total exposure limit) — the engine fails closed when a
    currency leg has no limit.
    """
    now = produced_at
    exposure_by_currency = dict(params.max_currency_exposure)
    for currency in sorted(currencies or set()):
        exposure_by_currency.setdefault(currency, params.max_total_exposure)
    return RiskPolicy(
        policy_id="paper-policy-v1",
        policy_version="1.0.0",
        max_risk_per_trade=params.max_risk_per_trade,
        strategy_risk_budgets={},
        max_total_exposure=params.max_total_exposure,
        max_instrument_exposure=params.max_instrument_exposure,
        max_asset_class_exposure={AssetClass.FX: params.max_total_exposure},
        max_currency_exposure=exposure_by_currency,
        max_leverage=params.max_leverage,
        margin_rates={AssetClass.FX: params.margin_rate_fx},
        max_positions=params.max_positions,
        max_pending_orders=params.max_pending_orders,
        max_daily_loss=params.max_daily_loss,
        max_drawdown_pct=params.max_drawdown_pct,
        max_consecutive_losses=params.max_consecutive_losses,
        cooldown_seconds=params.cooldown_seconds,
        max_spread_relative=params.max_spread_relative,
        max_slippage_relative=params.max_slippage_relative,
        min_stop_distance=params.min_stop_distance,
        market_data_max_age_seconds=params.market_data_max_age_seconds,
        heartbeat_max_age_seconds=params.heartbeat_max_age_seconds,
        min_position_size=params.min_position_size,
        max_position_size=params.max_position_size,
        instrument_whitelist=None,
        produced_at=now,
        provenance=Provenance(producer=CONFIG_PRODUCER, produced_at=now),
    )


def make_paper_venue(config: PaperPipelineConfig) -> PaperVenueConfig:
    venue = config.venue
    return PaperVenueConfig(
        trader_id=venue.trader_id,
        venue_name="PAPER",
        account_currency=config.account_currency,
        starting_balance=venue.starting_balance,
        seed=venue.seed,
        slippage_fixed_ticks=venue.slippage_fixed_ticks,
        slippage_random_min_ticks=venue.slippage_random_min_ticks,
        slippage_random_max_ticks=venue.slippage_random_max_ticks,
        commission_rate_bps=venue.commission_rate_bps,
        commission_min_amount=venue.commission_min_amount,
        prob_fill_on_limit=venue.prob_fill_on_limit,
        prob_fill_on_stop=venue.prob_fill_on_stop,
    )


def paper_fusion_config() -> FusionConfig:
    """Default calibrated fusion config for the paper pipeline.

    Equal weights over the canonical inputs (quant/llm/regime/memory), never
    arbitrary per-trade weights; the FLAT threshold keeps noise from trading.
    """
    bp = dict.fromkeys(INPUT_NAMES, 2500)
    return FusionConfig(
        name="paper-fusion-v1",
        version="paper-default-1",
        default_weights=ComponentWeights.from_dict(bp),
        flat_threshold=0.05,
        notes="Equal default weights over quant/llm/regime/memory; FLAT below 0.05.",
    )


def strategy_configuration(
    config: PaperPipelineConfig, produced_at: datetime
) -> StrategyConfiguration:
    """Point-in-time strategy configuration for the Risk Engine."""
    return StrategyConfiguration(
        strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        enabled=True,
        state=StrategyState.PAPER,
        allowed_instruments=frozenset(config.watchlist),
        as_of=produced_at,
        produced_at=produced_at,
        provenance=Provenance(producer=CONFIG_PRODUCER, produced_at=produced_at),
    )


def timeframe_for_interval(seconds: int) -> Timeframe:
    """Nearest canonical timeframe for a cycle interval (synthetic bars)."""
    if seconds <= 60:
        return Timeframe.M1
    if seconds <= 300:
        return Timeframe.M5
    if seconds <= 3600:
        return Timeframe.H1
    return Timeframe.H4
