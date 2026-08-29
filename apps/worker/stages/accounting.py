"""Accounting stage: deterministic account-state updates (Phase 7).

The *only* writer of ``PaperAccountRecord``. Updates flow exclusively from
canonical execution events:

- ``trade.closed`` — realized PnL, costs, balance, daily PnL, loss streak;
- ``position.updated`` — mark-to-market equity refresh.

A failed LLM analysis never reaches this module (INV-1); the risk engine reads
this record, so account state can never be corrupted by research failures.
CAS versioning makes concurrent updates impossible to silently overwrite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from core.domain.enums import PipelineStageName
from core.schemas import TradeOutcome
from core.schemas.events import DomainEvent
from core.schemas.pipeline import PaperAccountRecord

from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["AccountingStage"]

_PRODUCER = "apps.worker.accounting"


class AccountingStage(Stage):
    name = PipelineStageName.ACCOUNTING
    consumes = ("trade.closed", "position.updated")
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        account = rt.store.get_account(rt.config.account_id)
        if account is None:
            raise ValueError(f"paper account {rt.config.account_id!r} not initialized")
        now = rt.clock.now()

        if event.event_name == "trade.closed":
            outcome = TradeOutcome.model_validate(event.payload)
            account = self._apply_outcome(rt, account, outcome, now)
        else:
            account = self._refresh_equity(rt, account, now)

        rt.store.upsert_account(account, account.version - 1)
        exposure = Decimal("0")
        net_exposure = Decimal("0")
        for position in rt.ledger.open_positions():
            snapshot = rt.last_snapshot(position.instrument_id)
            mark = snapshot.mid if snapshot is not None else position.average_entry_price
            notional = position.quantity * mark
            exposure += notional
            net_exposure += notional if position.side.value == "LONG" else -notional
        drawdown = (
            max(Decimal("0"), account.peak_equity - account.equity) / account.peak_equity
            if account.peak_equity > 0
            else Decimal("0")
        )
        daily_limit = rt.policy.max_daily_loss
        risk_utilization = max(Decimal("0"), -account.daily_pnl) / daily_limit
        if event.trace_id is not None:
            rt.store.save_context_fragment(
                event.trace_id,
                "portfolio_snapshot",
                {
                    "as_of": now.isoformat(),
                    "gross_exposure": str(exposure),
                    "net_exposure": str(net_exposure),
                    "equity": str(account.equity),
                    "peak_equity": str(account.peak_equity),
                    "daily_loss": str(max(Decimal("0"), -account.daily_pnl)),
                    "drawdown": str(drawdown),
                    "open_positions": account.open_positions,
                },
                instrument_id=str(event.payload.get("instrument_id", "portfolio")),
                updated_at=now,
            )
        rt.operational_metrics.set_portfolio(
            pnl=float(account.realized_pnl),
            drawdown=float(drawdown),
            exposure=float(exposure),
            risk_utilization=float(risk_utilization),
            daily_loss=float(max(Decimal("0"), -account.daily_pnl)),
            daily_loss_limit=float(daily_limit),
            drawdown_limit=float(rt.policy.max_drawdown_pct),
        )
        rt.audit.record(
            "paper.account.updated",
            target=account.account_id,
            trace_id=event.trace_id,
            metadata={
                "balance": str(account.balance),
                "equity": str(account.equity),
                "realized_pnl": str(account.realized_pnl),
                "daily_pnl": str(account.daily_pnl),
                "consecutive_losses": account.consecutive_losses,
            },
        )
        return []

    # ── internals ─────────────────────────────────────────────────────────────

    def _apply_outcome(
        self,
        rt: StageRuntime,
        account: PaperAccountRecord,
        outcome: TradeOutcome,
        now: datetime,
    ) -> PaperAccountRecord:
        net = outcome.realized_pnl - outcome.costs
        realized = account.realized_pnl + net
        balance = rt.config.starting_balance + realized
        today = now.astimezone(UTC).date()
        last_update = account.updated_at.astimezone(UTC).date()
        daily_pnl = account.daily_pnl + net if last_update == today else net
        consecutive = account.consecutive_losses
        last_loss_at = account.last_loss_at
        if net < 0:
            consecutive += 1
            last_loss_at = now
        elif net > 0:
            consecutive = 0
        equity = balance + self._unrealized(rt)
        return account.model_copy(
            update={
                "balance": balance,
                "equity": equity,
                "realized_pnl": realized,
                "daily_pnl": daily_pnl,
                "peak_equity": max(account.peak_equity, equity),
                "consecutive_losses": consecutive,
                "last_loss_at": last_loss_at,
                "version": account.version + 1,
                "updated_at": now,
            }
        )

    def _refresh_equity(
        self, rt: StageRuntime, account: PaperAccountRecord, now: datetime
    ) -> PaperAccountRecord:
        equity = account.balance + self._unrealized(rt)
        return account.model_copy(
            update={
                "equity": equity,
                "peak_equity": max(account.peak_equity, equity),
                "version": account.version + 1,
                "updated_at": now,
            }
        )

    def _unrealized(self, rt: StageRuntime) -> Decimal:
        total = Decimal("0")
        for position in rt.ledger.open_positions():
            snapshot = rt.last_snapshot(position.instrument_id)
            mark = snapshot.mid if snapshot is not None else position.average_entry_price
            instrument = rt.instruments[position.instrument_id]
            delta = mark - position.average_entry_price
            from core.domain.enums import PositionSide

            if position.side is PositionSide.SHORT:
                delta = -delta
            pnl_quote = delta * position.quantity  # units x price delta
            quote = str(getattr(instrument, "quote_currency", rt.config.account_currency))
            if quote == rt.config.account_currency:
                total += pnl_quote
            else:
                base = str(getattr(instrument, "base_currency", ""))
                if base == rt.config.account_currency and mark > 0:
                    total += pnl_quote / mark
        return total
