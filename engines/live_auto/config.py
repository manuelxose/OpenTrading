"""Configuration for LIVE_AUTO governance (Phase 11).

``LiveAutoConfig`` mirrors the operator-set ``Settings`` values into a frozen,
validated document. It is disabled by default and fail-closed: enabling the
capability requires every limit (max strategies, max capital, max loss) to be
explicitly configured, so an accidental ``OT_LIVE_AUTO_ENABLED=true`` alone can
never authorize an automated order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from core.config.settings import Settings

__all__ = ["LiveAutoConfig", "LiveAutoViolation"]


class LiveAutoViolation(RuntimeError):
    """An automated order or a governance action violates LIVE_AUTO policy."""


@dataclass(frozen=True, slots=True)
class LiveAutoConfig:
    enabled: bool = False
    max_strategies: int = 0
    max_capital: Decimal | None = None
    max_loss: Decimal | None = None
    strategy_risk_budget_ceilings: Mapping[str, Decimal] = field(default_factory=dict)
    max_quote_age: timedelta = timedelta(seconds=5)
    max_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        if self.max_strategies < 0:
            raise ValueError("live_auto_max_strategies must be non-negative")
        if self.max_capital is not None and self.max_capital <= 0:
            raise ValueError("live_auto_max_capital must be positive")
        if self.max_loss is not None and self.max_loss <= 0:
            raise ValueError("live_auto_max_loss must be positive")
        for strategy_id, ceiling in self.strategy_risk_budget_ceilings.items():
            if not strategy_id:
                raise ValueError("live_auto strategy risk-budget keys must be non-empty")
            if ceiling <= 0:
                raise ValueError(f"live_auto risk-budget ceiling for {strategy_id!r} must be > 0")
        if self.max_quote_age <= timedelta(0):
            raise ValueError("live_auto max quote age must be positive")
        if self.max_quantity is not None and self.max_quantity <= 0:
            raise ValueError("live_auto max quantity must be positive")

    @classmethod
    def from_settings(cls, settings: Settings) -> LiveAutoConfig:
        return cls(
            enabled=settings.live_auto_enabled,
            max_strategies=settings.live_auto_max_strategies,
            max_capital=settings.live_auto_max_capital,
            max_loss=settings.live_auto_max_loss,
            strategy_risk_budget_ceilings=dict(settings.live_auto_strategy_risk_budgets),
            max_quote_age=timedelta(seconds=settings.live_max_quote_age_seconds),
            max_quantity=settings.live_max_quantity,
        )

    def assert_enabled(self) -> None:
        """Fail closed unless the capability is on AND every limit is explicit."""
        if not self.enabled:
            raise LiveAutoViolation(
                "LIVE_AUTO is disabled by configuration (OT_LIVE_AUTO_ENABLED is not true)"
            )
        if self.max_strategies < 1:
            raise LiveAutoViolation(
                "LIVE_AUTO requires OT_LIVE_AUTO_MAX_STRATEGIES >= 1 to be usable"
            )
        if self.max_capital is None or self.max_capital <= 0:
            raise LiveAutoViolation("LIVE_AUTO requires a positive OT_LIVE_AUTO_MAX_CAPITAL")
        if self.max_loss is None or self.max_loss <= 0:
            raise LiveAutoViolation("LIVE_AUTO requires a positive OT_LIVE_AUTO_MAX_LOSS")
