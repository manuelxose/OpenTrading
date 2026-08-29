from decimal import Decimal
from uuid import uuid4

from apps.worker.cli import build_default_config
from apps.worker.config import make_instrument, make_paper_policy, strategy_configuration
from apps.worker.sources import SyntheticSnapshotSource
from core.clock.clocks import SystemClock
from core.config.settings import get_settings
from core.domain.enums import OperatingMode, OrderType, SignalDirection
from core.schemas.base import Provenance
from core.schemas.risk import AccountState, PortfolioExposure, PortfolioState
from core.schemas.trading import TradeProposal
from engines.risk.sizing import compute_size_plan

clock = SystemClock()
config = build_default_config(get_settings())
inst = make_instrument(config.instruments["EURUSD"], clock.now())
src = SyntheticSnapshotSource(seed=42, instruments={"EURUSD": Decimal("1.10000")}, clock=clock)
snap = src.latest("EURUSD", now=clock.now(), step=1)
mid = snap.mid
atr = snap.high - snap.low
now = clock.now()
stop = (mid - atr * Decimal("1.5")).quantize(inst.tick_size)
take = (mid + atr * Decimal("3")).quantize(inst.tick_size)
proposal = TradeProposal(
    proposal_id=uuid4(),
    strategy_id="s",
    strategy_version="1",
    instrument_id="EURUSD",
    operating_mode=OperatingMode.PAPER,
    direction=SignalDirection.LONG,
    order_type=OrderType.MARKET,
    quantity=Decimal("1"),
    stop_loss=stop,
    take_profit=take,
    rationale="x",
    trace_id=None,
    produced_at=now,
    provenance=Provenance(producer="t", produced_at=now),
)
policy = make_paper_policy(config.risk, now)
account = AccountState(
    account_id=config.account_id,
    currency="USD",
    balance=Decimal(100000),
    equity=Decimal(100000),
    free_margin=Decimal(100000),
    leverage=Decimal(50),
    peak_equity=Decimal(100000),
    daily_pnl=Decimal(0),
    consecutive_losses=0,
    last_loss_at=None,
    broker_connected=True,
    last_heartbeat_at=now,
    safe_mode=False,
    as_of=snap.as_of,
    trace_id=None,
    produced_at=snap.as_of,
    provenance=Provenance(producer="t", produced_at=snap.as_of),
)
portfolio = PortfolioState(
    account_id=config.account_id,
    positions=[],
    pending_order_count=0,
    exposure=PortfolioExposure(),
    as_of=snap.as_of,
    trace_id=None,
    produced_at=snap.as_of,
    provenance=Provenance(producer="t", produced_at=snap.as_of),
)
strategy = strategy_configuration(config, snap.as_of)
plan = compute_size_plan(
    proposal=proposal,
    account=account,
    portfolio=portfolio,
    snapshot=snap,
    strategy=strategy,
    policy=policy,
    instrument=inst,
)
print("final", plan.final_quantity, "codes", plan.binding_codes, "below_min", plan.below_minimum)
print(
    "min_eff",
    plan.min_effective,
    "max_eff",
    plan.max_effective,
    "floor_applied",
    plan.floor_applied,
)
print(
    "entry",
    plan.entry_price,
    "stop_dist",
    plan.stop_distance,
    "risk_per_lot",
    plan.risk_per_lot,
    "budget",
    plan.effective_risk_budget,
)
