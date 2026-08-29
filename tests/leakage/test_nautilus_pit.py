"""Point-in-time (INV-3) leakage checks for the Nautilus replay.

The adapter must deliver bars to strategies strictly in timestamp order, with
nothing posterior to the current bar visible — the engine's virtual clock plus
the dataset define the only information a strategy can see.
"""

from __future__ import annotations

from decimal import Decimal

from adapters.nautilus.dataset import synthetic_dataset
from adapters.nautilus.engine import NautilusBacktestRunner
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_dt
from nautilus_trader.model.identifiers import Venue


class _Recorder:
    strategy_id = "pit-recorder"
    strategy_version = "1.0.0"

    def __init__(self) -> None:
        self.seen: list[tuple[int, Decimal, bool]] = []  # (ts_ns, close, is_last)

    def on_bar(self, ctx):
        self.seen.append((dt_to_unix_nanos(ctx.as_of), ctx.close, ctx.is_last_bar))
        return []


def test_replay_is_point_in_time_ordered(config) -> None:
    venue = Venue(config.venue_name)
    dataset = synthetic_dataset(config.dataset, config.instrument, config.spread, venue)
    recorder = _Recorder()
    result = NautilusBacktestRunner(config).run(recorder)
    assert result is not None

    expected = [(bar.ts_event, bar.close.as_decimal()) for bar in dataset.bars]
    got = [(ts_ns, close) for ts_ns, close, _ in recorder.seen]
    assert got == expected, "strategies must see exactly the historical bars, in order"

    timestamps = [ts_ns for ts_ns, _, _ in recorder.seen]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_only_the_last_bar_is_marked_last(config) -> None:
    recorder = _Recorder()
    NautilusBacktestRunner(config).run(recorder)
    last_flags = [is_last for _, _, is_last in recorder.seen]
    assert last_flags.count(True) == 1
    assert last_flags[-1] is True


def test_strategy_never_sees_beyond_dataset_end(config) -> None:
    venue = Venue(config.venue_name)
    dataset = synthetic_dataset(config.dataset, config.instrument, config.spread, venue)
    recorder = _Recorder()
    NautilusBacktestRunner(config).run(recorder)
    end_ns = dataset.bars[-1].ts_event
    for ts_ns, _, _ in recorder.seen:
        assert ts_ns <= end_ns
        assert unix_nanos_to_dt(ts_ns) <= dataset.end_time
