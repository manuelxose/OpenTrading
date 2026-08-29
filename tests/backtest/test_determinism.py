"""Definition of Done: dataset + config + code SHA ⇒ reproducible backtest result.

- same inputs twice ⇒ identical outputs (in-process and across processes);
- different seed ⇒ different outputs when randomness is enabled;
- input fingerprint binds dataset hash, config hash and code SHA.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from adapters.nautilus.engine import NautilusBacktestRunner
from adapters.nautilus.results import input_fingerprint

from conftest import make_config


def test_two_runs_produce_identical_outputs(config) -> None:
    first = NautilusBacktestRunner(config).run()
    second = NautilusBacktestRunner(config).run()
    assert first.output_hash == second.output_hash
    assert [r.canonical_dict() for r in first.execution_reports] == [
        r.canonical_dict() for r in second.execution_reports
    ]
    assert [o.canonical_dict() for o in first.trade_outcomes] == [
        o.canonical_dict() for o in second.trade_outcomes
    ]
    assert first.metrics == second.metrics


def test_input_fingerprint_binds_dataset_config_code(config) -> None:
    result = NautilusBacktestRunner(config).run()
    assert result.input_hash == input_fingerprint(
        result.dataset_hash, result.config_hash, result.code_sha
    )


def test_different_seed_gives_different_result_with_randomness() -> None:
    config_a = make_config(
        seed=42,
        slippage={"fixed_ticks": 1, "random_min_ticks": 0, "random_max_ticks": 2},
        rejection={"probability": 0.05},
    )
    config_b = make_config(
        seed=43,
        slippage={"fixed_ticks": 1, "random_min_ticks": 0, "random_max_ticks": 2},
        rejection={"probability": 0.05},
    )
    result_a = NautilusBacktestRunner(config_a).run()
    result_b = NautilusBacktestRunner(config_b).run()
    assert result_a.output_hash != result_b.output_hash


def test_no_randomness_runs_are_seed_independent_for_venue() -> None:
    """With zero random components, changing the venue seed must not change
    outcomes (the dataset itself is still seeded by its own seed)."""
    base = {
        "slippage": {"fixed_ticks": 1, "random_min_ticks": 0, "random_max_ticks": 0},
        "rejection": {"probability": 0.0},
    }
    config_a = make_config(seed=42, **base)
    config_b = make_config(seed=777, **base)
    result_a = NautilusBacktestRunner(config_a).run()
    result_b = NautilusBacktestRunner(config_b).run()
    assert result_a.trade_outcomes == result_b.trade_outcomes


def test_cross_process_reproducibility(config) -> None:
    """The CLI run in two separate processes prints identical output hashes."""
    cli = [sys.executable, "-m", "adapters.nautilus.cli", "--seed", "42"]
    out1 = subprocess.run(cli, capture_output=True, text=True, check=True).stdout.strip()
    out2 = subprocess.run(cli, capture_output=True, text=True, check=True).stdout.strip()
    first = json.loads(out1)
    second = json.loads(out2)
    assert first["output_hash"] == second["output_hash"]
    assert first["input_hash"] == second["input_hash"]


def test_parquet_replay_reproduces_synthetic_run(config, tmp_path: Path) -> None:
    """The same history replayed from parquet reproduces the same result."""
    from adapters.nautilus.dataset import synthetic_dataset
    from nautilus_trader.model.identifiers import Venue
    from parquet_helpers import write_bars_parquet

    venue = Venue(config.venue_name)
    dataset = synthetic_dataset(config.dataset, config.instrument, config.spread, venue)
    path = tmp_path / "replay.parquet"
    write_bars_parquet(dataset, path)

    synthetic_run = NautilusBacktestRunner(config).run()
    replay_config = config.model_copy(deep=True)
    replay_config.dataset.source = "parquet"
    replay_config.dataset.path = path
    replay_run = NautilusBacktestRunner(replay_config).run()
    assert replay_run.dataset_hash == synthetic_run.dataset_hash
    assert replay_run.output_hash == synthetic_run.output_hash
