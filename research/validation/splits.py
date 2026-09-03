"""Chronological data partitions and walk-forward windows (mandate §33, §34).

Financial time series are never shuffled here, and the final OOS partition is
handled as a one-shot resource: once results from it influence a parameter choice,
it is no longer out-of-sample and must be recorded as spent.

`OosLedger` exists to make that discipline mechanical rather than a matter of
memory. It is not security — it is a tripwire that leaves a record.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from research.strategies.xau_rpb.types import Bar

__all__ = [
    "OosLedger",
    "Partition",
    "Split",
    "WalkForwardWindow",
    "chronological_split",
    "walk_forward_windows",
]


@dataclass(frozen=True, slots=True)
class Partition:
    name: str
    start: datetime
    end: datetime
    bars: list[Bar]

    @property
    def span_days(self) -> int:
        return (self.end - self.start).days

    def describe(self) -> str:
        return (
            f"{self.name:12s} {self.start:%Y-%m-%d} -> {self.end:%Y-%m-%d} "
            f"({len(self.bars)} bars, {self.span_days / 365.25:.2f} years)"
        )


@dataclass(frozen=True, slots=True)
class Split:
    development: Partition
    validation: Partition
    final_oos: Partition

    def describe(self) -> str:
        return "\n".join(
            [
                self.development.describe(),
                self.validation.describe(),
                self.final_oos.describe(),
                "",
                "The FINAL OOS partition stays untouched until the rules and parameters",
                "are frozen. If it is consulted and then anything changes, it stops being",
                "out-of-sample and must be recorded as spent (see OosLedger).",
            ]
        )


def chronological_split(
    bars: Sequence[Bar],
    *,
    development_frac: float = 0.55,
    validation_frac: float = 0.20,
) -> Split:
    """Split strictly in time order (mandate §33). Never shuffled, never sampled."""
    if not bars:
        raise ValueError("cannot split an empty bar series")
    if development_frac <= 0 or validation_frac <= 0:
        raise ValueError("partition fractions must be > 0")
    if development_frac + validation_frac >= 1.0:
        raise ValueError("development + validation must leave a final OOS partition")

    ordered = sorted(bars, key=lambda b: b.time)
    n = len(ordered)
    dev_end = int(n * development_frac)
    val_end = dev_end + int(n * validation_frac)

    def part(name: str, chunk: list[Bar]) -> Partition:
        if not chunk:
            raise ValueError(f"partition '{name}' is empty; supply more history")
        return Partition(name, chunk[0].time, chunk[-1].time, chunk)

    return Split(
        development=part("DEVELOPMENT", ordered[:dev_end]),
        validation=part("VALIDATION", ordered[dev_end:val_end]),
        final_oos=part("FINAL_OOS", ordered[val_end:]),
    )


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    index: int
    train: list[Bar]
    test: list[Bar]
    anchored: bool

    @property
    def train_start(self) -> datetime:
        return self.train[0].time

    @property
    def train_end(self) -> datetime:
        return self.train[-1].time

    @property
    def test_start(self) -> datetime:
        return self.test[0].time

    @property
    def test_end(self) -> datetime:
        return self.test[-1].time

    def describe(self) -> str:
        kind = "anchored" if self.anchored else "rolling"
        return (
            f"W{self.index:02d} [{kind}] train {self.train_start:%Y-%m-%d}"
            f"->{self.train_end:%Y-%m-%d} ({len(self.train)}) | "
            f"test {self.test_start:%Y-%m-%d}->{self.test_end:%Y-%m-%d} ({len(self.test)})"
        )


def walk_forward_windows(
    bars: Sequence[Bar],
    *,
    train_months: int = 24,
    test_months: int = 6,
    anchored: bool = False,
) -> list[WalkForwardWindow]:
    """Build rolling or anchored walk-forward windows (mandate §34).

    Anchored windows keep the same start and grow the training set; rolling
    windows slide both edges. Comparing the two is how parameter stability —
    rather than aggregate P&L — becomes visible.
    """
    if not bars:
        return []
    ordered = sorted(bars, key=lambda b: b.time)
    start = ordered[0].time
    end = ordered[-1].time

    windows: list[WalkForwardWindow] = []
    train_delta = timedelta(days=int(train_months * 30.44))
    test_delta = timedelta(days=int(test_months * 30.44))

    index = 0
    train_start = start
    while True:
        train_end = train_start + train_delta
        test_end = train_end + test_delta
        if test_end > end:
            break

        effective_train_start = start if anchored else train_start
        train = [b for b in ordered if effective_train_start <= b.time < train_end]
        test = [b for b in ordered if train_end <= b.time < test_end]
        if train and test:
            windows.append(WalkForwardWindow(index, train, test, anchored))
            index += 1
        train_start = train_start + test_delta

    return windows


@dataclass(slots=True)
class OosLedger:
    """Records every consultation of the FINAL OOS partition (mandate §33).

    Once the final OOS has been read, any subsequent parameter change means the
    partition is spent. Storing the history makes that auditable instead of a
    claim.
    """

    path: Path
    entries: list[dict[str, str]] = field(default_factory=list)

    def load(self) -> None:
        if self.path.is_file():
            self.entries = json.loads(self.path.read_text(encoding="utf-8"))

    def record(self, *, config_hash: str, spec_version: str, reason: str) -> None:
        self.entries.append(
            {
                "consulted_at": datetime.now().isoformat(timespec="seconds"),
                "config_hash": config_hash,
                "spec_version": spec_version,
                "reason": reason,
            }
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, indent=2), encoding="utf-8")

    @property
    def is_spent(self) -> bool:
        """True once the OOS has been consulted with more than one configuration."""
        hashes = {e["config_hash"] for e in self.entries}
        return len(hashes) > 1

    def warning(self) -> str | None:
        if not self.entries:
            return None
        if self.is_spent:
            return (
                f"FINAL OOS IS SPENT: it has been consulted with {len(self.entries)} runs "
                f"across {len({e['config_hash'] for e in self.entries})} distinct "
                "configurations. Results from it are no longer out-of-sample and must "
                "be reported as in-sample research."
            )
        return (
            f"Final OOS consulted once ({self.entries[0]['config_hash']}). Any parameter "
            "change from here forward invalidates its out-of-sample status."
        )
