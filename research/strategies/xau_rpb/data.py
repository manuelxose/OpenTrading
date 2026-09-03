"""Market data loading and integrity validation (spec §31, §32).

The data quality report is a gate, not a formality. Every defect it can find has
produced a plausible-looking, wrong backtest somewhere: duplicated timestamps
inflate trade counts, gaps hide weekend risk, impossible OHLC silently changes
which side of a stop a bar touched, and a timezone mismatch moves every session
filter by an hour.

Nothing here fabricates data. If a file is absent, the loader says so.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .types import Bar

__all__ = ["DataQualityReport", "load_ohlc_csv", "validate_bars"]

_TIME_KEYS = ("time", "timestamp", "datetime", "date_time", "open_time")
_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)


@dataclass(slots=True)
class DataQualityReport:
    """Findings for one bar series (spec §32)."""

    source: str = ""
    bar_count: int = 0
    first_time: datetime | None = None
    last_time: datetime | None = None
    expected_interval_minutes: int = 0
    duplicate_timestamps: int = 0
    out_of_order: int = 0
    impossible_ohlc: int = 0
    non_positive_prices: int = 0
    negative_spreads: int = 0
    gaps: list[tuple[datetime, datetime, float]] = field(default_factory=list)
    largest_gap_hours: float = 0.0
    weekend_gaps: int = 0
    data_sha256: str = ""

    @property
    def span_years(self) -> float:
        if self.first_time is None or self.last_time is None:
            return 0.0
        return (self.last_time - self.first_time).days / 365.25

    @property
    def is_clean(self) -> bool:
        """Structural defects only. Gaps are reported, not automatically fatal."""
        return (
            self.duplicate_timestamps == 0
            and self.out_of_order == 0
            and self.impossible_ohlc == 0
            and self.non_positive_prices == 0
            and self.negative_spreads == 0
        )

    def summary(self) -> str:
        lines = [
            f"source                 : {self.source}",
            f"bars                   : {self.bar_count}",
            f"range                  : {self.first_time} -> {self.last_time}",
            f"span (years)           : {self.span_years:.2f}",
            f"expected interval (min): {self.expected_interval_minutes}",
            f"duplicate timestamps   : {self.duplicate_timestamps}",
            f"out-of-order bars      : {self.out_of_order}",
            f"impossible OHLC        : {self.impossible_ohlc}",
            f"non-positive prices    : {self.non_positive_prices}",
            f"negative spreads       : {self.negative_spreads}",
            f"gaps (> 2 intervals)   : {len(self.gaps)}",
            f"  of which weekend     : {self.weekend_gaps}",
            f"largest gap (hours)    : {self.largest_gap_hours:.2f}",
            f"data sha256            : {self.data_sha256}",
            f"CLEAN                  : {self.is_clean}",
        ]
        return "\n".join(lines)


def _parse_time(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in _FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _pick(row: dict[str, str], *names: str) -> str:
    for name in names:
        for key, value in row.items():
            if key and key.strip().lower() == name:
                return value
    return ""


def load_ohlc_csv(path: str | Path, *, spread_points_default: float = 0.0) -> list[Bar]:
    """Load OHLC bars from CSV.

    Accepts the usual MT4 export shapes: a single datetime column, or separate
    ``date`` and ``time`` columns, with optional ``volume`` and ``spread``.
    Rows that cannot be parsed are skipped rather than guessed at.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"OHLC file not found: {p}")

    bars: list[Bar] = []
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {p}")
        for row in reader:
            raw_time = _pick(row, *_TIME_KEYS)
            if not raw_time:
                date_part = _pick(row, "date")
                time_part = _pick(row, "time_only", "bar_time")
                raw_time = f"{date_part} {time_part}".strip()
            moment = _parse_time(raw_time)
            if moment is None:
                continue
            try:
                bar = Bar(
                    time=moment,
                    open=float(_pick(row, "open", "o")),
                    high=float(_pick(row, "high", "h")),
                    low=float(_pick(row, "low", "l")),
                    close=float(_pick(row, "close", "c")),
                    volume=float(_pick(row, "volume", "vol", "tickvol") or 0.0),
                    spread_points=float(_pick(row, "spread") or spread_points_default),
                )
            except (TypeError, ValueError):
                continue
            bars.append(bar)
    return bars


def validate_bars(
    bars: Sequence[Bar],
    *,
    expected_interval_minutes: int,
    source: str = "",
) -> DataQualityReport:
    """Produce the spec §32 data-quality report for a bar series."""
    report = DataQualityReport(
        source=source,
        bar_count=len(bars),
        expected_interval_minutes=expected_interval_minutes,
    )
    if not bars:
        return report

    report.first_time = bars[0].time
    report.last_time = bars[-1].time

    counts = Counter(b.time for b in bars)
    report.duplicate_timestamps = sum(c - 1 for c in counts.values() if c > 1)

    digest = hashlib.sha256()
    interval = timedelta(minutes=expected_interval_minutes)
    gap_threshold = interval * 2

    for i, bar in enumerate(bars):
        digest.update(
            f"{bar.time.isoformat()}|{bar.open}|{bar.high}|{bar.low}|{bar.close}".encode()
        )
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            report.non_positive_prices += 1
        elif not bar.is_valid():
            report.impossible_ohlc += 1
        if bar.spread_points < 0:
            report.negative_spreads += 1

        if i == 0:
            continue
        delta = bar.time - bars[i - 1].time
        if delta <= timedelta(0):
            report.out_of_order += 1
            continue
        if delta > gap_threshold:
            hours = delta.total_seconds() / 3600.0
            report.gaps.append((bars[i - 1].time, bar.time, hours))
            report.largest_gap_hours = max(report.largest_gap_hours, hours)
            # A Friday-close to Sunday/Monday-open gap is expected market structure.
            if bars[i - 1].time.weekday() >= 4 and bar.time.weekday() <= 0:
                report.weekend_gaps += 1

    report.data_sha256 = digest.hexdigest()[:16]
    return report
