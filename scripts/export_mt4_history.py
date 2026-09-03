"""Export MetaTrader 4 ``.hst`` history to the CSV format the research pipeline reads.

MT4 stores downloaded history in ``<data folder>/history/<server>/<SYMBOL><period>.hst``.
Format 401 (build 600+) is a 148-byte header followed by 60-byte records:

    int64  ctm          bar open time, BROKER SERVER time (not UTC)
    double open, high, low, close
    int64  tick_volume
    int32  spread
    int64  real_volume

Two things this exporter is deliberately explicit about:

* **Timestamps are broker server time.** They are exported unchanged, and the
  server's UTC offset is recorded in the sidecar so the session layer can
  normalize correctly (spec §11). Silently treating them as UTC would shift every
  session boundary.
* **Spread is almost always 0 in downloaded history.** MT4 does not retain
  per-bar spread for history it back-fills from the broker. When the column is
  empty the exporter writes a MODELLED constant and records that fact in the
  sidecar, so no downstream report can mistake a modelled spread for an observed
  one.

Usage:

    python scripts/export_mt4_history.py --list
    python scripts/export_mt4_history.py --symbol XAUUSD --period 15 --out data/market/
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

HEADER_SIZE = 148
RECORD_401 = 60
RECORD_400 = 44
TERMINAL_ROOT = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"


@dataclass
class HistoryMeta:
    """Everything needed to reproduce and correctly interpret an export."""

    source_file: str
    server: str
    data_folder: str
    symbol: str
    period_minutes: int
    digits: int
    format_version: int
    bars: int
    first_bar_broker_time: str
    last_bar_broker_time: str
    span_years: float
    timestamps_are: str
    broker_utc_offset_hours: float | None
    spread_source: str
    spread_points: float | None
    data_sha256: str
    exported_at: str


def find_data_folders() -> list[tuple[Path, str]]:
    """Return ``(data_folder, terminal_path)`` for every MT4 installation found."""
    out: list[tuple[Path, str]] = []
    if not TERMINAL_ROOT.is_dir():
        return out
    for folder in sorted(TERMINAL_ROOT.iterdir()):
        origin = folder / "origin.txt"
        if not origin.is_file():
            continue
        raw = origin.read_bytes()
        # origin.txt is UTF-16LE with a BOM.
        try:
            text = raw.decode("utf-16").strip().lstrip("﻿")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", "replace").strip()
        if (folder / "history").is_dir():
            out.append((folder, text))
    return out


def list_history(data_folder: Path) -> list[tuple[str, Path]]:
    history = data_folder / "history"
    found: list[tuple[str, Path]] = []
    if not history.is_dir():
        return found
    for server_dir in sorted(history.iterdir()):
        if not server_dir.is_dir():
            continue
        for hst in sorted(server_dir.glob("*.hst")):
            found.append((server_dir.name, hst))
    return found


def read_hst(path: Path) -> tuple[dict[str, object], list[tuple]]:
    """Parse an ``.hst`` file into a header dict and a list of bar tuples."""
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"{path.name}: shorter than a header")

    version, = struct.unpack_from("<i", raw, 0)
    symbol = raw[68:80].split(b"\0")[0].decode("ascii", "replace")
    period, digits = struct.unpack_from("<ii", raw, 80)

    body = raw[HEADER_SIZE:]
    if version >= 401:
        record, layout = RECORD_401, "<q4dqiq"
    else:
        record, layout = RECORD_400, "<i4dii"

    count = len(body) // record
    bars: list[tuple] = []
    for i in range(count):
        fields = struct.unpack_from(layout, body, i * record)
        if version >= 401:
            ctm, open_, high, low, close, volume, spread, _real = fields
        else:
            ctm, open_, high, low, close, volume, spread = (*fields, 0)
        bars.append((int(ctm), open_, high, low, close, float(volume), int(spread)))

    header = {
        "version": version,
        "symbol": symbol,
        "period": period,
        "digits": digits,
    }
    return header, bars


def export(
    hst: Path,
    out_dir: Path,
    *,
    server: str,
    data_folder: Path,
    assumed_spread_points: float,
    broker_utc_offset_hours: float | None,
) -> HistoryMeta:
    header, bars = read_hst(hst)
    if not bars:
        raise ValueError(f"{hst.name}: no bars")

    observed_spread = any(b[6] > 0 for b in bars)
    spread_source = "observed (from .hst)" if observed_spread else "MODELLED CONSTANT"

    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(header["symbol"])
    period = int(header["period"])
    # The data-folder id is part of the name: two terminals can carry the SAME
    # server name (one per installation), and without it the second export
    # silently overwrites the first.
    stem = f"{symbol}_M{period}_{server}_{data_folder.name[:8]}"
    csv_path = out_dir / f"{stem}.csv"

    digest = hashlib.sha256()
    with csv_path.open("w", encoding="ascii", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["time", "open", "high", "low", "close", "volume", "spread"])
        for ctm, o, h, low, c, vol, spread in bars:
            moment = datetime.fromtimestamp(ctm, UTC).replace(tzinfo=None)
            spread_points = float(spread) if observed_spread else assumed_spread_points
            writer.writerow([
                moment.strftime("%Y.%m.%d %H:%M"),
                f"{o:.5f}", f"{h:.5f}", f"{low:.5f}", f"{c:.5f}",
                f"{vol:.0f}", f"{spread_points:.1f}",
            ])
            digest.update(f"{ctm}|{o}|{h}|{low}|{c}".encode())

    first = datetime.fromtimestamp(bars[0][0], UTC).replace(tzinfo=None)
    last = datetime.fromtimestamp(bars[-1][0], UTC).replace(tzinfo=None)

    meta = HistoryMeta(
        source_file=str(hst),
        server=server,
        data_folder=str(data_folder),
        symbol=symbol,
        period_minutes=period,
        digits=int(header["digits"]),
        format_version=int(header["version"]),
        bars=len(bars),
        first_bar_broker_time=first.isoformat(sep=" "),
        last_bar_broker_time=last.isoformat(sep=" "),
        span_years=round((last - first).days / 365.25, 3),
        timestamps_are="BROKER SERVER TIME (not UTC)",
        broker_utc_offset_hours=broker_utc_offset_hours,
        spread_source=spread_source,
        spread_points=None if observed_spread else assumed_spread_points,
        data_sha256=digest.hexdigest()[:16],
        exported_at=datetime.now().isoformat(timespec="seconds"),
    )
    (out_dir / f"{stem}.meta.json").write_text(
        json.dumps(asdict(meta), indent=2), encoding="utf-8"
    )
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export MT4 .hst history to CSV")
    parser.add_argument("--list", action="store_true", help="list available history")
    parser.add_argument("--symbol", help="symbol to export, e.g. XAUUSD")
    parser.add_argument("--period", type=int, default=15, help="period in minutes")
    parser.add_argument("--server", help="restrict to one server folder")
    parser.add_argument("--out", default="data/market", help="output directory")
    parser.add_argument(
        "--assumed-spread-points", type=float, default=20.0,
        help="spread written when the .hst carries none (MT4 usually stores 0)",
    )
    parser.add_argument(
        "--broker-utc-offset", type=float, default=None,
        help="server UTC offset, recorded in the sidecar for the session layer",
    )
    args = parser.parse_args(argv)

    folders = find_data_folders()
    if not folders:
        print("no MT4 data folders found under %APPDATA%/MetaQuotes/Terminal",
              file=sys.stderr)
        return 2

    if args.list:
        for data_folder, terminal in folders:
            print(f"\n{data_folder.name}  ->  {terminal}")
            for server, hst in list_history(data_folder):
                try:
                    header, bars = read_hst(hst)
                except (ValueError, struct.error) as exc:
                    print(f"    {server}/{hst.name}: unreadable ({exc})")
                    continue
                if not bars:
                    print(f"    {server}/{hst.name}: empty")
                    continue
                first = datetime.fromtimestamp(bars[0][0], UTC)
                last = datetime.fromtimestamp(bars[-1][0], UTC)
                years = (last - first).days / 365.25
                print(f"    {server}/{hst.name}: {header['symbol']} "
                      f"M{header['period']} {len(bars)} bars "
                      f"{first:%Y-%m-%d}->{last:%Y-%m-%d} ({years:.2f}y)")
        return 0

    if not args.symbol:
        parser.error("--symbol is required unless --list is given")

    exported = 0
    for data_folder, _terminal in folders:
        for server, hst in list_history(data_folder):
            if args.server and server != args.server:
                continue
            if hst.stem.upper() != f"{args.symbol.upper()}{args.period}":
                continue
            meta = export(
                hst, Path(args.out), server=server, data_folder=data_folder,
                assumed_spread_points=args.assumed_spread_points,
                broker_utc_offset_hours=args.broker_utc_offset,
            )
            stem = f"{meta.symbol}_M{meta.period_minutes}_{server}_{data_folder.name[:8]}"
            print(f"exported {meta.bars} bars -> {Path(args.out) / (stem + '.csv')}")
            print(f"  symbol={meta.symbol} M{meta.period_minutes} digits={meta.digits}")
            print(f"  range  {meta.first_bar_broker_time} -> {meta.last_bar_broker_time} "
                  f"({meta.span_years} years, BROKER SERVER TIME)")
            print(f"  spread {meta.spread_source}"
                  + (f" = {meta.spread_points} points" if meta.spread_points else ""))
            print(f"  sha256 {meta.data_sha256}")
            exported += 1

    if not exported:
        print(f"no history found for {args.symbol} M{args.period}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
