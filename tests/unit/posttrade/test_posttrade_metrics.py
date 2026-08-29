"""Deterministic metric math for the post-trade learning loop (architecture §17)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from core.domain.enums import SignalDirection
from core.schemas import TradeOutcome
from engines.posttrade.metrics import (
    MetricsInput,
    PricePoint,
    brier_error,
    compute_trade_metrics,
    direction_correct,
)

from factories import make_trade_outcome

ENTRY = Decimal("1.08000")
EXIT = Decimal("1.08500")
OPEN_AT = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)
CLOSE_AT = OPEN_AT + timedelta(hours=2)


def long_winner_path() -> tuple[PricePoint, ...]:
    return (
        PricePoint(
            ts=OPEN_AT + timedelta(minutes=30),
            high=Decimal("1.08300"),
            low=Decimal("1.07850"),
            close=Decimal("1.08200"),
        ),
        PricePoint(
            ts=OPEN_AT + timedelta(minutes=60),
            high=Decimal("1.08800"),
            low=Decimal("1.07900"),
            close=Decimal("1.08650"),
        ),
    )


def long_outcome(**overrides) -> TradeOutcome:
    return make_trade_outcome(
        OPEN_AT,
        entry_price=ENTRY,
        exit_price=EXIT,
        realized_pnl=Decimal("46.00"),
        costs=Decimal("4.00"),
        opened_at=OPEN_AT,
        closed_at=CLOSE_AT,
        direction=SignalDirection.LONG,
        **overrides,
    )


class TestSignedReturn:
    def test_long_win(self) -> None:
        from engines.posttrade.metrics import signed_return_pct

        assert signed_return_pct(ENTRY, EXIT, SignalDirection.LONG) == pytest.approx(
            0.46296, abs=1e-3
        )

    def test_short_win(self) -> None:
        from engines.posttrade.metrics import signed_return_pct

        assert signed_return_pct(EXIT, ENTRY, SignalDirection.SHORT) == pytest.approx(
            0.46082, abs=1e-3
        )


class TestDirectionCorrectness:
    def test_long_up(self) -> None:
        assert direction_correct(SignalDirection.LONG, True) is True
        assert direction_correct(SignalDirection.LONG, False) is False

    def test_short_down(self) -> None:
        assert direction_correct(SignalDirection.SHORT, False) is True
        assert direction_correct(SignalDirection.SHORT, True) is False

    def test_flat_never_correct(self) -> None:
        assert direction_correct(SignalDirection.FLAT, True) is None
        assert direction_correct(None, False) is None


class TestBrierError:
    def test_confident_hit(self) -> None:
        assert brier_error(1.0, True) == pytest.approx(0.0)

    def test_confident_miss_penalized(self) -> None:
        assert brier_error(1.0, False) == pytest.approx(1.0)

    def test_timid(self) -> None:
        assert brier_error(0.5, True) == pytest.approx(0.25)

    def test_missing_confidence(self) -> None:
        assert brier_error(None, True) is None


class TestComputeMetrics:
    def test_long_winner_full_surface(self) -> None:
        metrics = compute_trade_metrics(
            MetricsInput(
                outcome=long_outcome(),
                risk_amount=Decimal("20.00"),
                expected_return_pct=0.30,
                path=long_winner_path(),
                regime="trend_up",
                signal_calibration_error={"quant": 0.16},
                planned_stop=Decimal("1.07800"),
                planned_take=Decimal("1.08600"),
            )
        )
        assert metrics.pnl_gross == Decimal("46.00")
        assert metrics.pnl_net == Decimal("42.00")
        assert metrics.fees == Decimal("4.00")
        assert metrics.r_multiple == pytest.approx(2.1)
        assert metrics.holding_seconds == 7200
        assert metrics.market_regime == "trend_up"
        assert metrics.signal_calibration_error == {"quant": 0.16}
        # MAE from path lows, MFE from path highs.
        assert metrics.mae_pct == pytest.approx(float((ENTRY - Decimal("1.07850")) / ENTRY * 100))
        assert metrics.mfe_pct == pytest.approx(float((Decimal("1.08800") - ENTRY) / ENTRY * 100))
        # best = max high; entry efficiency captures the favorable extreme.
        best = Decimal("1.08800")
        assert metrics.entry_efficiency == pytest.approx(float((EXIT - ENTRY) / (best - ENTRY)))
        # exit efficiency is clamped in [0, 1].
        assert metrics.exit_efficiency is not None
        assert 0.0 <= metrics.exit_efficiency <= 1.0
        # alpha = actual - expected.
        assert metrics.alpha_pct == pytest.approx(metrics.actual_return_pct - 0.30)
        assert metrics.prediction_error_pct == pytest.approx(abs(metrics.actual_return_pct - 0.30))
        assert metrics.expected_r == pytest.approx(
            float(abs(Decimal("1.08600") - ENTRY) / abs(Decimal("1.07800") - ENTRY))
        )

    def test_short_winner_excursions_inverted(self) -> None:
        outcome = make_trade_outcome(
            OPEN_AT,
            direction=SignalDirection.SHORT,
            entry_price=Decimal("1.08500"),
            exit_price=Decimal("1.08000"),
            realized_pnl=Decimal("46.00"),
            costs=Decimal("0"),
            opened_at=OPEN_AT,
            closed_at=CLOSE_AT,
        )
        path = (
            PricePoint(
                ts=OPEN_AT,
                high=Decimal("1.09000"),
                low=Decimal("1.08000"),
                close=Decimal("1.08100"),
            ),
        )
        metrics = compute_trade_metrics(MetricsInput(outcome=outcome, path=path))
        assert metrics.mae_pct == pytest.approx(
            float((Decimal("1.09000") - Decimal("1.08500")) / Decimal("1.08500") * 100)
        )
        assert metrics.mfe_pct == pytest.approx(
            float((Decimal("1.08500") - Decimal("1.08000")) / Decimal("1.08500") * 100)
        )

    def test_no_path_never_fabricates_excursions(self) -> None:
        metrics = compute_trade_metrics(MetricsInput(outcome=long_outcome()))
        assert metrics.mae_pct is None
        assert metrics.mfe_pct is None
        assert metrics.entry_efficiency is None
        assert metrics.exit_efficiency is None

    def test_missing_risk_amount_yields_no_r_multiple(self) -> None:
        metrics = compute_trade_metrics(MetricsInput(outcome=long_outcome(), risk_amount=None))
        assert metrics.r_multiple is None

    def test_zero_risk_amount_guarded(self) -> None:
        metrics = compute_trade_metrics(
            MetricsInput(outcome=long_outcome(), risk_amount=Decimal("0"))
        )
        assert metrics.r_multiple is None

    def test_benchmark_alpha_overrides_plan_alpha(self) -> None:
        metrics = compute_trade_metrics(
            MetricsInput(
                outcome=long_outcome(),
                expected_return_pct=0.30,
                benchmark_return_pct=0.10,
            )
        )
        assert metrics.alpha_pct == pytest.approx(metrics.actual_return_pct - 0.10)

    def test_unknown_regime_default(self) -> None:
        metrics = compute_trade_metrics(MetricsInput(outcome=long_outcome()))
        assert metrics.market_regime == "unknown"
