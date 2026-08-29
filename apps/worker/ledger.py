"""Paper ledger: authoritative position & account accounting for the PAPER
venue (Phase 7).

The ledger is the *only* place that turns fills into account state:

- net position per instrument (NETTING venue semantics, like the Nautilus
  backtest router);
- positions persisted through the execution state store (``ExecutionPosition``
  rows survive restarts — the ledger rebuilds from them);
- realized PnL and costs update the paper account record through the pipeline
  store's compare-and-set (``PaperAccountRecord``);
- a fully-closed position yields a canonical :class:`TradeOutcome`.

A failed LLM analysis never reaches this module: it only consumes
``ExecutionReport`` / ``TradeOutcome`` produced by the deterministic execution
path (INV-1, INV-4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from core.clock.clocks import Clock, SystemClock
from core.domain.enums import OrderSide, PositionSide, SignalDirection
from core.schemas import ExecutionPosition, ExecutionReport, MarketSnapshot, PositionSnapshot
from core.schemas.base import Provenance
from core.schemas.pipeline import PaperAccountRecord
from core.schemas.risk import AccountState, PortfolioExposure, PortfolioState
from core.schemas.trading import OrderIntent, TradeOutcome
from engines.posttrade.metrics import PricePoint

__all__ = ["FillApplication", "LedgerPosition", "PaperLedger"]

_PRODUCER = "apps.worker.ledger"

#: Upper bound on observed path points per position (memory safety).
_MAX_PATH_POINTS = 20_000


@dataclass
class LedgerPosition:
    """Net position for one instrument (NETTING semantics)."""

    instrument_id: str
    side: PositionSide
    quantity: Decimal  # units
    average_entry_price: Decimal
    opened_at: datetime
    venue_position_id: str = ""
    order_intent_ids: list[UUID] = field(default_factory=list)
    entry_costs: Decimal = Decimal("0")
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None


@dataclass(frozen=True)
class FillApplication:
    """Outcome of applying one fill report to the ledger."""

    position: PositionSnapshot | None
    outcome: TradeOutcome | None
    realized_pnl: Decimal
    costs: Decimal


class PaperLedger:
    """Deterministic position and account accounting for the paper venue."""

    def __init__(
        self,
        *,
        account_id: str,
        currency: str,
        lot_size: Decimal,
        instrument_by_id: dict[str, object],
        execution_store: object,
        clock: Clock | None = None,
    ) -> None:
        self._account_id = account_id
        self._currency = currency
        self._lot_size = lot_size
        self._instrument_by_id = instrument_by_id
        self._execution_store = execution_store
        self._clock = clock or SystemClock()
        self._positions: dict[str, LedgerPosition] = {}
        self._outcomes: list[TradeOutcome] = []
        self._paths: dict[str, list[PricePoint]] = {}

    # ── reconstruction after restart ──────────────────────────────────────────

    def load(self, open_positions: tuple[ExecutionPosition, ...]) -> None:
        """Rebuild in-memory net positions from persisted execution state."""
        self._positions = {}
        for persisted in open_positions:
            if persisted.closed_at is not None:
                continue
            self._positions[persisted.instrument_id] = LedgerPosition(
                instrument_id=persisted.instrument_id,
                side=persisted.side,
                quantity=persisted.quantity,
                average_entry_price=persisted.average_entry_price,
                opened_at=persisted.opened_at,
                venue_position_id=persisted.venue_position_id,
                order_intent_ids=[persisted.order_intent_id] if persisted.order_intent_id else [],
                entry_costs=Decimal("0"),
            )

    # ── position queries ──────────────────────────────────────────────────────

    def position(self, instrument_id: str) -> LedgerPosition | None:
        return self._positions.get(instrument_id)

    def open_positions(self) -> list[LedgerPosition]:
        return list(self._positions.values())

    def outcomes(self) -> list[TradeOutcome]:
        return list(self._outcomes)

    # ── observed price path (MAE/MFE source for the learning loop) ─────────

    def record_mark(self, snapshot: MarketSnapshot) -> None:
        """Append one observed price point to the open position's path.

        Bounded (``_MAX_PATH_POINTS``): the tracker is a lossy rolling window,
        never an unbounded price history (heavy history lives in MinIO).
        """
        position = self._positions.get(snapshot.instrument_id)
        if position is None or not position.venue_position_id:
            return
        mid = snapshot.mid
        point = PricePoint(
            ts=snapshot.as_of,
            high=snapshot.high if snapshot.high is not None else mid,
            low=snapshot.low if snapshot.low is not None else mid,
            close=snapshot.close if snapshot.close is not None else mid,
        )
        path = self._paths.setdefault(position.venue_position_id, [])
        path.append(point)
        if len(path) > _MAX_PATH_POINTS:
            del path[: len(path) - _MAX_PATH_POINTS]

    def price_path(self, position_id: str) -> tuple[PricePoint, ...]:
        """The observed path for a (possibly closed) position."""
        return tuple(self._paths.get(position_id, ()))

    def clear_price_path(self, position_id: str) -> None:
        self._paths.pop(position_id, None)

    def snapshots(
        self, marks: dict[str, Decimal], now: datetime | None = None
    ) -> list[PositionSnapshot]:
        """Canonical position snapshots with current marks (portfolio state)."""
        now = now or self._clock.now()
        snapshots: list[PositionSnapshot] = []
        for position in self._positions.values():
            mark = marks.get(position.instrument_id, position.average_entry_price)
            unrealized = self._unrealized(position, mark)
            snapshots.append(
                PositionSnapshot(
                    position_id=self._position_id(position.instrument_id),
                    account_id=self._account_id,
                    strategy_id=None,
                    instrument_id=position.instrument_id,
                    side=position.side,
                    quantity=position.quantity,
                    average_entry_price=position.average_entry_price,
                    mark_price=mark,
                    unrealized_pnl=unrealized,
                    as_of=now,
                    trace_id=None,
                    produced_at=now,
                    provenance=Provenance(producer=_PRODUCER, produced_at=now),
                )
            )
        return snapshots

    def marks(self, snapshots: dict[str, MarketSnapshot]) -> dict[str, Decimal]:
        return {instrument_id: snapshot.mid for instrument_id, snapshot in snapshots.items()}

    # ── fill application ──────────────────────────────────────────────────────

    def apply_fill(
        self,
        report: ExecutionReport,
        intent: OrderIntent,
        *,
        trace_id: UUID | None,
    ) -> FillApplication:
        """Apply one FILLED/partial fill report; net the position; close on
        sign flip. Persists the resulting ``ExecutionPosition`` through the
        provided sink callback (the caller owns the store transaction)."""
        if report.filled_quantity <= 0:
            raise ValueError("apply_fill requires a positive filled_quantity")
        fill_price = report.average_fill_price
        if fill_price is None:
            raise ValueError("apply_fill requires average_fill_price")
        multiplier = self._units_multiplier(intent.instrument_id)
        current = self._positions.get(intent.instrument_id)
        realized = Decimal("0")

        if current is None or current.side == self._side_of(intent.side):
            # Opening or adding to an existing position (same side).
            if current is None:
                current = LedgerPosition(
                    instrument_id=intent.instrument_id,
                    side=self._side_of(intent.side),
                    quantity=report.filled_quantity,
                    average_entry_price=fill_price,
                    opened_at=report.report_time,
                    venue_position_id=self._new_position_id(intent.instrument_id),
                    order_intent_ids=[intent.order_intent_id],
                    entry_costs=report.commission,
                )
                self._positions[intent.instrument_id] = current
                position = self._persist_position(current, closed=False)
                return FillApplication(
                    position=position,
                    outcome=None,
                    realized_pnl=Decimal("0"),
                    costs=report.commission,
                )
            total = current.quantity + report.filled_quantity
            current.average_entry_price = (
                current.average_entry_price * current.quantity + fill_price * report.filled_quantity
            ) / total
            current.quantity = total
            current.entry_costs += report.commission
            current.order_intent_ids.append(intent.order_intent_id)
            position = self._persist_position(current, closed=False)
            return FillApplication(
                position=position, outcome=None, realized_pnl=Decimal("0"), costs=report.commission
            )

        # Closing leg: reduce the opposite position.
        closed_qty = min(current.quantity, report.filled_quantity)
        delta = fill_price - current.average_entry_price
        if current.side is PositionSide.LONG:
            pnl_quote = delta * closed_qty * multiplier
        else:
            pnl_quote = -delta * closed_qty * multiplier
        realized = self._to_account_currency(pnl_quote, intent.instrument_id, fill_price)

        remaining = current.quantity - report.filled_quantity
        if remaining <= 0:
            # Full close: the closing intent joins the entry intents so the
            # outcome carries every order of the trade (postmortem traceability).
            current.order_intent_ids.append(intent.order_intent_id)
            outcome = self._build_outcome(current, closed_qty, fill_price, report, trace_id)
            self._positions.pop(intent.instrument_id, None)
            self._outcomes.append(outcome)
            persisted = self._persist_position(current, closed=True)
            return FillApplication(
                position=persisted, outcome=outcome, realized_pnl=realized, costs=report.commission
            )
        current.quantity = remaining
        current.entry_costs += report.commission
        persisted = self._persist_position(current, closed=False)
        return FillApplication(
            position=persisted, outcome=None, realized_pnl=realized, costs=report.commission
        )

    # ── account & portfolio views (Risk Engine inputs) ───────────────────────

    def account_state(
        self, account: PaperAccountRecord, now: datetime | None = None
    ) -> AccountState:
        now = now or self._clock.now()
        return AccountState(
            account_id=account.account_id,
            currency=account.currency,
            balance=account.balance,
            equity=account.equity,
            free_margin=account.equity,
            leverage=Decimal("50"),
            peak_equity=account.peak_equity,
            daily_pnl=account.daily_pnl,
            consecutive_losses=account.consecutive_losses,
            last_loss_at=account.last_loss_at,
            broker_connected=True,
            last_heartbeat_at=now,
            safe_mode=False,
            as_of=now,
            trace_id=None,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

    def portfolio_state(
        self,
        account: PaperAccountRecord,
        marks: dict[str, Decimal],
        pending_orders: int,
        now: datetime | None = None,
    ) -> PortfolioState:
        now = now or self._clock.now()
        positions = self.snapshots(marks, now)
        total_notional = Decimal("0")
        by_instrument: dict[str, Decimal] = {}
        net_by_currency: dict[str, Decimal] = {}
        for position in self._positions.values():
            instrument = self._instrument_by_id[position.instrument_id]
            mark = marks.get(position.instrument_id, position.average_entry_price)
            notional = position.quantity * mark  # units x price (quote ccy)
            total_notional += notional
            by_instrument[position.instrument_id] = notional
            quote = str(getattr(instrument, "quote_currency", ""))
            sign = Decimal("1") if position.side is PositionSide.LONG else Decimal("-1")
            net_by_currency[quote] = net_by_currency.get(quote, Decimal("0")) + sign * notional
        exposure = PortfolioExposure(
            total_notional=total_notional,
            by_instrument=by_instrument,
            by_asset_class={},
            net_by_currency=net_by_currency,
        )
        return PortfolioState(
            account_id=account.account_id,
            positions=positions,
            pending_order_count=pending_orders,
            exposure=exposure,
            as_of=now,
            trace_id=None,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _side_of(side: OrderSide) -> PositionSide:
        return PositionSide.LONG if side is OrderSide.BUY else PositionSide.SHORT

    @staticmethod
    def _position_id(instrument_id: str) -> str:
        return f"paper:{instrument_id}"

    @staticmethod
    def _new_position_id(instrument_id: str) -> str:
        """Unique venue position id per opening (keeps closed rows in the
        execution store for the full audit history)."""
        return f"paper:{instrument_id}:{uuid4().hex[:12]}"

    def _persist_position(self, position: LedgerPosition, *, closed: bool) -> PositionSnapshot:
        now = self._clock.now()
        venue_position_id = position.venue_position_id or self._new_position_id(
            position.instrument_id
        )
        position.venue_position_id = venue_position_id
        persisted = ExecutionPosition(
            venue_position_id=venue_position_id,
            account_id=self._account_id,
            instrument_id=position.instrument_id,
            side=position.side,
            quantity=position.quantity,
            average_entry_price=position.average_entry_price,
            order_intent_id=position.order_intent_ids[-1] if position.order_intent_ids else None,
            opened_at=position.opened_at,
            updated_at=now,
            closed_at=now if closed else None,
        )
        self._execution_store.upsert_position(persisted)  # type: ignore[attr-defined]
        return PositionSnapshot(
            position_id=persisted.venue_position_id,
            account_id=persisted.account_id,
            strategy_id=None,
            instrument_id=persisted.instrument_id,
            side=persisted.side,
            quantity=persisted.quantity,
            average_entry_price=persisted.average_entry_price,
            mark_price=persisted.average_entry_price,
            unrealized_pnl=Decimal("0"),
            as_of=now,
            trace_id=None,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

    def _unrealized(self, position: LedgerPosition, mark: Decimal) -> Decimal:
        delta = mark - position.average_entry_price
        if position.side is PositionSide.SHORT:
            delta = -delta
        pnl_quote = delta * position.quantity  # units x price delta
        return self._to_account_currency(pnl_quote, position.instrument_id, mark)

    def _to_account_currency(
        self, pnl_quote: Decimal, instrument_id: str, at_price: Decimal
    ) -> Decimal:
        instrument = self._instrument_by_id[instrument_id]
        quote = str(getattr(instrument, "quote_currency", self._currency))
        base = str(getattr(instrument, "base_currency", ""))
        if quote == self._currency:
            return pnl_quote
        if base == self._currency:
            # pnl is in quote currency; convert through the current price.
            if at_price <= 0:
                return pnl_quote
            return pnl_quote / at_price
        raise NotImplementedError(
            f"paper ledger supports accounts in quote/base currency only "
            f"(account={self._currency}, pair={base}/{quote})"
        )

    def _build_outcome(
        self,
        position: LedgerPosition,
        closed_qty: Decimal,
        exit_price: Decimal,
        report: ExecutionReport,
        trace_id: UUID | None,
    ) -> TradeOutcome:
        now = self._clock.now()
        costs = position.entry_costs + report.commission
        entry = position.average_entry_price
        if position.side is PositionSide.LONG:
            gross = (
                (exit_price - entry) * closed_qty * self._units_multiplier(position.instrument_id)
            )
        else:
            gross = (
                (entry - exit_price) * closed_qty * self._units_multiplier(position.instrument_id)
            )
        realized = self._to_account_currency(gross, position.instrument_id, exit_price)
        return TradeOutcome(
            trade_id=report.execution_report_id,
            position_id=position.venue_position_id or self._position_id(position.instrument_id),
            order_intent_ids=[str(i) for i in position.order_intent_ids],
            instrument_id=position.instrument_id,
            direction=SignalDirection.LONG
            if position.side is PositionSide.LONG
            else SignalDirection.SHORT,
            quantity=closed_qty,
            entry_price=entry,
            exit_price=exit_price,
            realized_pnl=realized,
            costs=costs,
            slippage_total=None,
            r_multiple=None,
            holding_seconds=None,
            opened_at=position.opened_at,
            closed_at=now,
            exit_reason="position_closed",
            produced_at=now,
            trace_id=trace_id,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

    def _units_multiplier(self, instrument_id: str) -> Decimal:
        """Quantities are already in tradeable units (matching Nautilus FX
        spot); realized/unrealized PnL is delta x units in quote currency."""
        return Decimal("1")
