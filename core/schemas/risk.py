"""Risk & Policy contracts consumed by the deterministic Risk Engine (INV-4).

``RiskPolicy`` is a versioned, immutable policy document; ``AccountState``,
``PortfolioState`` and ``StrategyConfiguration`` are point-in-time inputs that
the pipeline snapshots before evaluation (INV-3).

All monetary limits are denominated in the account currency; the engine
approximates the proposal's notional in the instrument quote currency (see
ADR-0018 for the denomination assumption and its follow-up FX-rates work).
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Self

from pydantic import Field, field_validator, model_validator

from core.domain.enums import AssetClass, StrategyState
from core.schemas.base import BaseContractModel, DomainObject, UtcDateTime
from core.schemas.trading import PositionSnapshot

__all__ = [
    "TRADABLE_STRATEGY_STATES",
    "AccountState",
    "PortfolioExposure",
    "PortfolioState",
    "RiskPolicy",
    "StrategyConfiguration",
]

CURRENCY_PATTERN = r"^[A-Z]{3}$"

#: Strategy lifecycle states in which a strategy may trade at all (INV-8).
#: Research states (IDEA … ROBUSTNESS_OK) and RETIRED never produce live orders.
TRADABLE_STRATEGY_STATES: frozenset[StrategyState] = frozenset(
    {
        StrategyState.PAPER,
        StrategyState.SHADOW,
        StrategyState.LIVE_GATED,
        StrategyState.LIVE_AUTO,
    }
)


class RiskPolicy(DomainObject):
    """Versioned risk policy. Every numeric limit is explicit — no implicit defaults.

    ``instrument_whitelist=None`` means unrestricted; an explicit (possibly empty)
    frozenset is a strict whitelist.
    """

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)

    # ── per-trade risk ────────────────────────────────────────────────────────
    max_risk_per_trade: Decimal = Field(gt=0)
    strategy_risk_budgets: dict[str, Decimal] = Field(default_factory=dict)

    # ── exposure (notional) ───────────────────────────────────────────────────
    max_total_exposure: Decimal = Field(gt=0)
    max_instrument_exposure: Decimal = Field(gt=0)
    max_asset_class_exposure: dict[AssetClass, Decimal] = Field(default_factory=dict)
    max_currency_exposure: dict[str, Decimal] = Field(default_factory=dict)
    max_leverage: Decimal = Field(gt=0)
    margin_rates: dict[AssetClass, Decimal] = Field(default_factory=dict)

    # ── simultaneity ──────────────────────────────────────────────────────────
    max_positions: int = Field(ge=1)
    max_pending_orders: int = Field(ge=1)

    # ── loss controls ─────────────────────────────────────────────────────────
    max_daily_loss: Decimal = Field(gt=0)
    max_drawdown_pct: Decimal = Field(gt=0, lt=1)
    max_consecutive_losses: int = Field(ge=1)
    cooldown_seconds: int = Field(ge=0)

    # ── market quality ────────────────────────────────────────────────────────
    max_spread_relative: Decimal = Field(ge=0)
    max_slippage_relative: Decimal = Field(ge=0)
    min_stop_distance: Decimal = Field(gt=0)
    market_data_max_age_seconds: int = Field(ge=0)
    heartbeat_max_age_seconds: int = Field(ge=0)

    # ── size ──────────────────────────────────────────────────────────────────
    min_position_size: Decimal | None = Field(default=None, gt=0)
    max_position_size: Decimal | None = Field(default=None, gt=0)

    # ── eligibility & schedule ────────────────────────────────────────────────
    instrument_whitelist: frozenset[str] | None = None
    trading_days: frozenset[int] = frozenset(range(7))
    session_open_utc: time | None = None
    session_close_utc: time | None = None

    @field_validator("strategy_risk_budgets")
    @classmethod
    def _budgets_positive(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        for strategy_id, budget in value.items():
            if not strategy_id:
                raise ValueError("strategy_risk_budgets keys must be non-empty")
            if budget <= 0:
                raise ValueError(f"risk budget for {strategy_id!r} must be > 0")
        return value

    @field_validator("max_asset_class_exposure")
    @classmethod
    def _class_exposure_positive(
        cls, value: dict[AssetClass, Decimal]
    ) -> dict[AssetClass, Decimal]:
        for asset_class, limit in value.items():
            if limit <= 0:
                raise ValueError(f"exposure limit for {asset_class.value} must be > 0")
        return value

    @field_validator("max_currency_exposure")
    @classmethod
    def _currency_keys_valid(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        import re

        for currency, limit in value.items():
            if not re.fullmatch(CURRENCY_PATTERN, currency):
                raise ValueError(f"invalid currency code {currency!r}")
            if limit <= 0:
                raise ValueError(f"exposure limit for {currency} must be > 0")
        return value

    @field_validator("margin_rates")
    @classmethod
    def _margin_rates_valid(cls, value: dict[AssetClass, Decimal]) -> dict[AssetClass, Decimal]:
        for asset_class, rate in value.items():
            if not 0 < rate < 1:
                raise ValueError(f"margin rate for {asset_class.value} must be in (0, 1)")
        return value

    @field_validator("trading_days")
    @classmethod
    def _trading_days_valid(cls, value: frozenset[int]) -> frozenset[int]:
        if not value <= frozenset(range(7)):
            raise ValueError("trading_days must be a subset of weekdays 0..6 (Mon..Sun)")
        return value

    @model_validator(mode="after")
    def _check_policy_shape(self) -> Self:
        # Margin coverage: every asset class the policy may trade must have a rate.
        missing = set(self.max_asset_class_exposure) - set(self.margin_rates)
        if missing:
            names = ", ".join(sorted(ac.value for ac in missing))
            raise ValueError(f"margin_rates missing for asset classes: {names}")
        if (self.session_open_utc is None) != (self.session_close_utc is None):
            raise ValueError("session_open_utc and session_close_utc must be set together")
        if (
            self.min_position_size is not None
            and self.max_position_size is not None
            and self.min_position_size > self.max_position_size
        ):
            raise ValueError("min_position_size must be <= max_position_size")
        return self


class PortfolioExposure(BaseContractModel):
    """Pre-computed aggregate exposures of the current portfolio (engines/portfolio).

    ``by_*`` values are gross notional per bucket; ``net_by_currency`` is the
    signed net notional per currency (long base adds, short base subtracts).
    """

    total_notional: Decimal = Field(default=Decimal("0"), ge=0)
    by_instrument: dict[str, Decimal] = Field(default_factory=dict)
    by_asset_class: dict[AssetClass, Decimal] = Field(default_factory=dict)
    net_by_currency: dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("by_instrument", "by_asset_class")
    @classmethod
    def _gross_non_negative(cls, value: dict[object, Decimal]) -> dict[object, Decimal]:
        for key, notional in value.items():
            if notional < 0:
                raise ValueError(f"gross notional for {key!r} must be >= 0")
        return value


class PortfolioState(DomainObject):
    """Point-in-time portfolio state: open positions, pending orders, exposure."""

    account_id: str = Field(min_length=1)
    positions: list[PositionSnapshot] = Field(default_factory=list)
    pending_order_count: int = Field(default=0, ge=0)
    exposure: PortfolioExposure
    as_of: UtcDateTime

    @model_validator(mode="after")
    def _check_exposure_consistency(self) -> Self:
        position_ids = {position.instrument_id for position in self.positions}
        if set(self.exposure.by_instrument) != position_ids:
            raise ValueError("exposure.by_instrument keys must match position instrument ids")
        for position in self.positions:
            if position.account_id != self.account_id:
                raise ValueError("positions must belong to the portfolio account")
        return self


class AccountState(DomainObject):
    """Point-in-time account state (INV-3). All fields are Decimals — never floats."""

    account_id: str = Field(min_length=1)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    balance: Decimal = Field(ge=0)
    equity: Decimal = Field(gt=0)
    free_margin: Decimal = Field(ge=0)
    leverage: Decimal = Field(gt=0)
    peak_equity: Decimal = Field(gt=0)
    daily_pnl: Decimal
    consecutive_losses: int = Field(ge=0)
    last_loss_at: UtcDateTime | None = None
    broker_connected: bool = True
    last_heartbeat_at: UtcDateTime | None = None
    safe_mode: bool = False
    as_of: UtcDateTime

    @model_validator(mode="after")
    def _check_loss_streak(self) -> Self:
        if self.consecutive_losses > 0 and self.last_loss_at is None:
            raise ValueError("consecutive_losses > 0 requires last_loss_at")
        return self


class StrategyConfiguration(DomainObject):
    """Point-in-time strategy configuration snapshot.

    ``allowed_instruments=None`` means unrestricted; an explicit frozenset is a
    per-strategy whitelist applied on top of the policy whitelist.
    """

    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    enabled: bool
    state: StrategyState
    allowed_instruments: frozenset[str] | None = None
    as_of: UtcDateTime
