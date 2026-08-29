"""Market contracts: ``Instrument`` and ``MarketSnapshot``."""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from core.domain.enums import AssetClass, Timeframe
from core.schemas.base import DomainObject, UtcDateTime

__all__ = ["Instrument", "MarketSnapshot"]


class Instrument(DomainObject):
    """Static description of a tradable instrument (symbol rules, lot rules)."""

    instrument_id: str = Field(pattern=r"^[A-Z0-9._/-]{1,32}$")
    symbol: str = Field(min_length=1, max_length=64)
    exchange: str = Field(min_length=1, max_length=64)
    asset_class: AssetClass
    base_currency: str | None = None
    quote_currency: str | None = None
    price_precision: int = Field(ge=0, le=8)
    tick_size: Decimal = Field(gt=0)
    lot_size: Decimal = Field(gt=0)
    lot_step: Decimal = Field(gt=0)
    min_lot: Decimal = Field(gt=0)
    max_lot: Decimal = Field(gt=0)
    contract_size: Decimal = Field(default=Decimal("1"), gt=0)
    is_active: bool = True

    @model_validator(mode="after")
    def _check_lot_ordering(self) -> Self:
        if self.min_lot > self.max_lot:
            raise ValueError("min_lot must be <= max_lot")
        return self


class MarketSnapshot(DomainObject):
    """Point-in-time market state for one instrument (INV-3).

    ``as_of`` is the simulation/query time anchor; ``source_timestamp`` is the
    exchange timestamp. Nothing posterior to ``as_of`` may influence decisions.
    """

    instrument_id: str = Field(min_length=1)
    as_of: UtcDateTime
    source_timestamp: UtcDateTime
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    last: Decimal | None = Field(default=None, gt=0)
    open: Decimal | None = Field(default=None, gt=0)
    high: Decimal | None = Field(default=None, gt=0)
    low: Decimal | None = Field(default=None, gt=0)
    close: Decimal | None = Field(default=None, gt=0)
    volume: Decimal | None = Field(default=None, ge=0)
    timeframe: Timeframe | None = None
    source: str = Field(min_length=1, description="Raw data producer (e.g. broker feed)")

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        if self.source_timestamp > self.as_of:
            raise ValueError("source_timestamp must not be later than as_of (INV-3)")
        return self

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2
