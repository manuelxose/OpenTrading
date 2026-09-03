"""Deterministic unit tests for the LIVE_AUTO supervisor engine (no sockets)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from adapters.mt4.protocol import MarketQuote, Mt4MessageType
from apps.live_supervisor.config import (
    LiveSupervisorConfig,
    build_instrument,
    build_live_policy,
    build_strategy_configuration,
)
from apps.live_supervisor.engine import LiveTradingEngine
from apps.live_supervisor.signals import MinuteBarSeries, ScalpParams, momentum_signal
from core.domain.enums import (
    OperatingMode,
    OrderSide,
    PositionSide,
    SignalDirection,
)
from core.schemas import PositionSnapshot, Provenance
from core.schemas.risk import AccountState, PortfolioExposure, PortfolioState
from engines.execution.live_gate import PriceContext
from engines.risk.engine import evaluate_proposal

T0 = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


def make_config() -> LiveSupervisorConfig:
    return LiveSupervisorConfig(
        strategy_id="baseline-momentum-live-001",
        strategy_version="1.0.0",
        instruments=("BTCUSD", "ETHUSD"),
        cycle_interval_seconds=300,
        position_equity_pct=Decimal("0.02"),
        stop_atr_ratio=Decimal("1.5"),
        take_atr_ratio=Decimal("3.0"),
        max_open_positions=1,
        max_spread_points=Decimal("1000"),
        risk_per_trade=Decimal("100"),
        min_strength=Decimal("0.0002"),
        persist_bars=False,
        signal_params=ScalpParams(
            fast_ema=12, slow_ema=45, atr_period=14, min_strength=Decimal("0.0002")
        ),
    )


def make_account(equity: Decimal = Decimal("51000")) -> AccountState:
    return AccountState(
        account_id="44961955",
        currency="USD",
        balance=Decimal("51000"),
        equity=equity,
        free_margin=Decimal("50800"),
        leverage=Decimal("100"),
        peak_equity=Decimal("51000"),
        daily_pnl=Decimal("0"),
        consecutive_losses=0,
        last_loss_at=None,
        broker_connected=True,
        last_heartbeat_at=T0,
        safe_mode=False,
        as_of=T0,
        produced_at=T0,
        provenance=Provenance(producer="test", produced_at=T0),
    )


def make_quote(symbol: str, bid: Decimal, ask: Decimal, observed_at: datetime) -> MarketQuote:
    return MarketQuote(
        message_type=Mt4MessageType.MARKET_QUOTE,
        message_id=uuid4(),
        timestamp=observed_at,
        sequence=1,
        symbol=symbol,
        bid=bid,
        ask=ask,
        spread=ask - bid,
        tradable=True,
    )


def warm_series(
    series: MinuteBarSeries,
    start_price: Decimal,
    step: Decimal,
    minutes: int,
    start_at: datetime,
) -> Decimal:
    price = start_price
    for i in range(minutes):
        observed = start_at + timedelta(minutes=i)
        price += step
        for tick in range(4):
            series.on_price(price + Decimal(tick % 2) * Decimal("0.10"), observed + timedelta(seconds=tick * 15))
    return price


def warm_engine(engine: LiveTradingEngine, minutes: int = 100) -> None:
    start = T0 - timedelta(minutes=minutes)
    price = Decimal("78000")
    step = Decimal("2")
    series = MinuteBarSeries()
    warm_series(series, price, step, minutes, start)
    engine._series["BTCUSD"] = series  # replace the internal series directly


class CapturingSubmitter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, PriceContext, object]] = []

    def submit(self, intent, *, price_context, risk_decision) -> object:
        self.calls.append((intent, price_context, risk_decision))
        return "ok"


# ── signals ────────────────────────────────────────────────────────────────
def test_momentum_signal_rises_and_falls() -> None:
    rising = MinuteBarSeries()
    warm_series(rising, Decimal("100.00"), Decimal("0.05"), 120, T0 - timedelta(minutes=120))
    up = momentum_signal(rising, Decimal("0.0002"))
    assert up.direction is SignalDirection.LONG
    assert up.strength > 0

    falling = MinuteBarSeries()
    warm_series(falling, Decimal("100.00"), Decimal("-0.05"), 120, T0 - timedelta(minutes=120))
    down = momentum_signal(falling, Decimal("0.0002"))
    assert down.direction is SignalDirection.SHORT
    assert down.strength < 0


# ── engine cycle ───────────────────────────────────────────────────────────
def test_engine_approves_and_submits_on_strong_signal() -> None:
    config = make_config()
    clock = FakeClock(T0)
    submitter = CapturingSubmitter()
    policy = build_live_policy(config, T0)
    engine = LiveTradingEngine(
        config,
        clock,
        submitter,
        policy=policy,
        instruments={"BTCUSD": build_instrument("BTCUSD", T0), "ETHUSD": build_instrument("ETHUSD", T0)},
        strategy=build_strategy_configuration(config, T0),
    )
    warm_engine(engine, minutes=120)
    bid = Decimal("78120.00")
    ask = Decimal("78120.20")
    quote = make_quote("BTCUSD", bid, ask, T0 - timedelta(seconds=1))
    account = make_account()
    portfolio = PortfolioState(
        account_id="44961955",
        positions=[],
        pending_order_count=0,
        exposure=PortfolioExposure(),
        as_of=T0,
        produced_at=T0,
        provenance=Provenance(producer="test", produced_at=T0),
    )
    outcomes = engine.cycle(account=account, portfolio=portfolio, quotes={"BTCUSD": quote})
    assert len(submitter.calls) == 1
    intent, price_context, decision = submitter.calls[0]
    assert intent.operating_mode is OperatingMode.LIVE_AUTO
    assert intent.side is OrderSide.BUY
    assert intent.quantity == decision.approved_quantity
    assert intent.stop_loss == decision.approved_stop
    assert intent.quantity >= Decimal("0.01")
    assert price_context.bid == bid and price_context.ask == ask
    assert outcomes and outcomes[0].decision in ("APPROVE", "RESIZE")


def test_engine_skips_stale_quote() -> None:
    config = make_config()
    clock = FakeClock(T0)
    submitter = CapturingSubmitter()
    engine = LiveTradingEngine(
        config, clock, submitter,
        policy=build_live_policy(config, T0),
        instruments={"BTCUSD": build_instrument("BTCUSD", T0)},
        strategy=build_strategy_configuration(config, T0),
    )
    warm_engine(engine, minutes=120)
    stale = make_quote("BTCUSD", Decimal("78120.00"), Decimal("78120.40"), T0 - timedelta(minutes=5))
    outcomes = engine.cycle(
        account=make_account(),
        portfolio=PortfolioState(
            account_id="44961955", positions=[], pending_order_count=0,
            exposure=PortfolioExposure(), as_of=T0, produced_at=T0,
            provenance=Provenance(producer="test", produced_at=T0),
        ),
        quotes={"BTCUSD": stale},
    )
    assert not submitter.calls
    assert any(outcome.decision == "SKIP" for outcome in outcomes)


def test_engine_skips_when_position_open() -> None:
    config = make_config()
    clock = FakeClock(T0)
    submitter = CapturingSubmitter()
    engine = LiveTradingEngine(
        config, clock, submitter,
        policy=build_live_policy(config, T0),
        instruments={"BTCUSD": build_instrument("BTCUSD", T0)},
        strategy=build_strategy_configuration(config, T0),
    )
    warm_engine(engine, minutes=120)
    open_position = PositionSnapshot(
        position_id="mt4-1",
        account_id="44961955",
        strategy_id=config.strategy_id,
        instrument_id="BTCUSD",
        side=PositionSide.LONG,
        quantity=Decimal("0.01"),
        average_entry_price=Decimal("78000"),
        mark_price=Decimal("78120"),
        as_of=T0,
        produced_at=T0,
        provenance=Provenance(producer="test", produced_at=T0),
    )
    exposure = PortfolioExposure(
        total_notional=Decimal("781.2"), by_instrument={"BTCUSD": Decimal("781.2")},
        by_asset_class={}, net_by_currency={"USD": Decimal("781.2")},
    )
    portfolio = PortfolioState(
        account_id="44961955", positions=[open_position], pending_order_count=0,
        exposure=exposure, as_of=T0, produced_at=T0,
        provenance=Provenance(producer="test", produced_at=T0),
    )
    quote = make_quote("BTCUSD", Decimal("78120.00"), Decimal("78120.20"), T0 - timedelta(seconds=1))
    outcomes = engine.cycle(account=make_account(), portfolio=portfolio, quotes={"BTCUSD": quote})
    assert not submitter.calls
    assert any("open position" in outcome.detail for outcome in outcomes)


def test_risk_engine_approves_deterministic_proposal() -> None:
    config = make_config()
    policy = build_live_policy(config, T0)
    instrument = build_instrument("BTCUSD", T0)
    strategy = build_strategy_configuration(config, T0)
    engine = LiveTradingEngine(
        config, FakeClock(T0), CapturingSubmitter(),
        policy=policy, instruments={"BTCUSD": instrument}, strategy=strategy,
    )
    warm_engine(engine, minutes=120)
    series = engine._series["BTCUSD"]
    sig = momentum_signal(series, config.min_strength)
    assert sig.tradable
    proposal = engine._build_proposal(
        "BTCUSD", instrument, sig, make_quote("BTCUSD", Decimal("78120.00"), Decimal("78120.40"), T0 - timedelta(seconds=1)), T0, Decimal("51000")
    )
    from core.schemas import MarketSnapshot

    snapshot = MarketSnapshot(
        instrument_id="BTCUSD", as_of=T0, source_timestamp=T0 - timedelta(seconds=1),
        bid=Decimal("78120.00"), ask=Decimal("78120.40"), last=Decimal("78120.20"),
        high=Decimal("78120.40"), low=Decimal("78120.00"), close=Decimal("78120.20"),
        source="test", produced_at=T0,
        provenance=Provenance(producer="test", produced_at=T0),
    )
    decision = evaluate_proposal(
        proposal=proposal,
        account=make_account(),
        portfolio=PortfolioState(
            account_id="44961955", positions=[], pending_order_count=0,
            exposure=PortfolioExposure(), as_of=T0, produced_at=T0,
            provenance=Provenance(producer="test", produced_at=T0),
        ),
        snapshot=snapshot,
        strategy=strategy,
        policy=policy,
        instrument=instrument,
    )
    assert decision.decision.value in ("APPROVE", "RESIZE")
    assert decision.approved_quantity is not None and decision.approved_quantity >= Decimal("0.01")
    assert decision.approved_stop is not None


# ── Strategy Lab (offline self-improvement) ───────────────────────────────
def _trend_bars(start: Decimal, step: Decimal, count: int) -> tuple[MinuteBarSeries, Decimal]:
    series = MinuteBarSeries()
    price = start
    for i in range(count):
        observed = T0 + timedelta(minutes=i)
        price += step
        series.on_price(price - Decimal("2"), observed)
        series.on_price(price + Decimal("2"), observed + timedelta(seconds=15))
        series.on_price(price, observed + timedelta(seconds=30))
        series.on_price(price + (Decimal("1") if step >= 0 else Decimal("-1")), observed + timedelta(seconds=45))
    return series, price


def test_replay_uptrend_wins_with_aggressive_scalp() -> None:
    from apps.live_supervisor.signals import PriceBar
    from apps.strategy_lab.evaluator import replay

    series, _ = _trend_bars(Decimal("78000"), Decimal("20"), 300)
    bars = [
        PriceBar(open=b.open, high=b.high, low=b.low, close=b.close, closed_at=b.closed_at)
        for b in series.bars()
    ]
    params = ScalpParams(
        fast_ema=5, slow_ema=13, atr_period=7, min_strength=Decimal("0.00005")
    )
    result = replay(
        bars, params, stop_ratio=Decimal("1.2"), take_ratio=Decimal("2.0"), spread=Decimal("5")
    )
    assert result.trades > 0
    assert result.total_pnl > 0
    assert result.wins / result.trades >= Decimal("0.9")  # aggressive scalp in a clean trend


def test_replay_downtrend_profits_short() -> None:
    from apps.live_supervisor.signals import PriceBar
    from apps.strategy_lab.evaluator import replay

    series, _ = _trend_bars(Decimal("78000"), Decimal("-20"), 300)
    bars = [
        PriceBar(open=b.open, high=b.high, low=b.low, close=b.close, closed_at=b.closed_at)
        for b in series.bars()
    ]
    params = ScalpParams(
        fast_ema=5, slow_ema=13, atr_period=7, min_strength=Decimal("0.00005")
    )
    result = replay(
        bars, params, stop_ratio=Decimal("1.2"), take_ratio=Decimal("2.0"), spread=Decimal("5")
    )
    assert result.trades > 0
    assert result.total_pnl > 0


def test_scalp_signal_uses_parametrized_windows() -> None:
    series, _ = _trend_bars(Decimal("100.00"), Decimal("0.20"), 120)
    aggressive = ScalpParams(
        fast_ema=5, slow_ema=13, atr_period=7, min_strength=Decimal("0.00005")
    )
    from apps.live_supervisor.signals import scalp_signal

    signal = scalp_signal(series, aggressive)
    assert signal.direction is SignalDirection.LONG


def test_evaluate_grid_ranks_best_candidate_first() -> None:
    from apps.live_supervisor.signals import PriceBar
    from apps.strategy_lab.lab import ScalpingGrid, evaluate_grid

    series, _ = _trend_bars(Decimal("78000"), Decimal("20"), 300)
    bars = [
        PriceBar(open=b.open, high=b.high, low=b.low, close=b.close, closed_at=b.closed_at)
        for b in series.bars()
    ]
    grid = ScalpingGrid(
        fast_ema=(5, 8),
        slow_ema=(13, 21),
        atr_period=(7,),
        min_strength=(Decimal("0.0001"),),
        stop_ratio=(Decimal("1.2"),),
        take_ratio=(Decimal("2.0"), Decimal("3.0")),
    )
    candidates = evaluate_grid(bars, grid, spread=Decimal("5"))
    assert candidates
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)
    assert candidates[0].result.trades > 0


# ── quote collector: backlog draining (regression) ─────────────────────────
class BackloggedQuoteClient:
    """Fake client with a backlog of stale quotes followed by fresh ones."""

    def __init__(self, backlog: int, fresh: int, now: datetime) -> None:
        self._queue: list[tuple[str, MarketQuote]] = []
        for i in range(backlog):
            stale = make_quote("BTCUSD", Decimal("78120.00"), Decimal("78120.20"), now - timedelta(seconds=60 + i))
            self._queue.append(("BTCUSD", stale))
        for i in range(fresh):
            self._queue.append(
                ("BTCUSD", make_quote("BTCUSD", Decimal("78120.00"), Decimal("78120.20"), now - timedelta(milliseconds=100)))
            )

    def poll_quote(self, timeout_ms: int = 0):
        if self._queue:
            return self._queue.pop(0)
        return None


def test_collector_drains_backlog_and_returns_fresh_quote() -> None:
    from apps.live_supervisor.supervisor import collect_latest_quotes

    client = BackloggedQuoteClient(backlog=500, fresh=3, now=T0)
    quotes = collect_latest_quotes(client, ("BTCUSD",), max_wait_ms=3000, idle_stop_ms=100)
    assert "BTCUSD" in quotes
    age = T0 - quotes["BTCUSD"].timestamp
    assert age < timedelta(seconds=30)  # freshest frame wins, not the backlog head
