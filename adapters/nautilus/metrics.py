"""End-of-run portfolio metrics (architecture §20, costs included).

Computed deterministically from domain ``TradeOutcome`` objects and the equity
curve — the same code path serves BACKTEST and PAPER.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import sqrt

from core.schemas import TradeOutcome
from pydantic import BaseModel, Field

__all__ = ["EquityPoint", "PortfolioMetrics", "compute_metrics"]


class EquityPoint(BaseModel):
    ts: datetime
    equity: Decimal


class PortfolioMetrics(BaseModel):
    """Cost-inclusive end-of-run metrics in the account currency."""

    initial_equity: Decimal
    ending_equity: Decimal
    net_profit: Decimal
    gross_profit: Decimal = Field(ge=0)
    gross_loss: Decimal = Field(le=0)
    total_commission: Decimal = Field(ge=0)
    total_slippage: Decimal = Field(ge=0)
    n_trades: int = Field(ge=0)
    n_wins: int = Field(ge=0)
    n_losses: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    profit_factor: float | None = Field(default=None, ge=0)
    return_pct: float
    max_drawdown_pct: float = Field(ge=0)
    sharpe_ratio: float | None = None
    n_bars: int = Field(ge=0)


def compute_metrics(
    outcomes: list[TradeOutcome],
    equity_curve: list[EquityPoint],
    bars_per_year: float,
) -> PortfolioMetrics:
    """Derive cost-inclusive metrics from closed trades and the equity curve."""
    net_pnls = [outcome.realized_pnl - outcome.costs for outcome in outcomes]
    wins = [pnl for pnl in net_pnls if pnl > 0]
    losses = [pnl for pnl in net_pnls if pnl < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    total_commission = sum((o.costs for o in outcomes), Decimal("0"))
    total_slippage = sum((o.slippage_total or Decimal("0") for o in outcomes), Decimal("0"))
    n_wins, n_losses = len(wins), len(losses)
    win_rate = n_wins / len(net_pnls) if net_pnls else 0.0
    profit_factor: float | None = None
    if gross_loss < 0:
        profit_factor = float(gross_profit / abs(gross_loss))
    elif gross_profit > 0:
        profit_factor = float("inf")

    initial = equity_curve[0].equity if equity_curve else Decimal("0")
    ending = equity_curve[-1].equity if equity_curve else Decimal("0")
    # Trading PnL net of costs (realized - commission). The equity curve delta
    # additionally includes base-currency revaluation, hence the separate fields.
    net_profit = gross_profit + gross_loss
    return_pct = float((ending - initial) / initial * 100) if initial else 0.0
    max_drawdown_pct = _max_drawdown_pct(equity_curve)
    sharpe = _sharpe_ratio(equity_curve, bars_per_year)

    return PortfolioMetrics(
        initial_equity=initial,
        ending_equity=ending,
        net_profit=net_profit,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_commission=total_commission,
        total_slippage=total_slippage,
        n_trades=len(net_pnls),
        n_wins=n_wins,
        n_losses=n_losses,
        win_rate=win_rate,
        profit_factor=profit_factor,
        return_pct=return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe,
        n_bars=len(equity_curve),
    )


def _max_drawdown_pct(equity_curve: list[EquityPoint]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].equity
    max_dd = Decimal("0")
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            dd = (peak - point.equity) / peak
            max_dd = max(max_dd, dd)
    return float(max_dd * 100)


def _sharpe_ratio(equity_curve: list[EquityPoint], bars_per_year: float) -> float | None:
    """Per-bar simple returns, annualized by sqrt(bars/year)."""
    if len(equity_curve) < 3 or bars_per_year <= 0:
        return None
    returns: list[float] = []
    previous = equity_curve[0].equity
    for point in equity_curve[1:]:
        if previous > 0:
            returns.append(float((point.equity - previous) / previous))
        previous = point.equity
    if not returns:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    return mean_return / sqrt(variance) * sqrt(bars_per_year)
