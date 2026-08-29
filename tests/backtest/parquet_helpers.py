"""Helper: write Nautilus bars to parquet losslessly (decimal price columns)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from adapters.nautilus.dataset import Dataset

PRICE_TYPE = pa.decimal128(15, 5)


def write_bars_parquet(dataset: Dataset, path: Path) -> None:
    """Persist bars with exact decimal prices so dataset hashes survive a round-trip."""
    table = pa.Table.from_pydict(
        {
            "ts_event": pa.array([bar.ts_event for bar in dataset.bars], type=pa.int64()),
            "open": pa.array([bar.open.as_decimal() for bar in dataset.bars], type=PRICE_TYPE),
            "high": pa.array([bar.high.as_decimal() for bar in dataset.bars], type=PRICE_TYPE),
            "low": pa.array([bar.low.as_decimal() for bar in dataset.bars], type=PRICE_TYPE),
            "close": pa.array([bar.close.as_decimal() for bar in dataset.bars], type=PRICE_TYPE),
            "volume": pa.array(
                [int(bar.volume.as_decimal()) for bar in dataset.bars], type=pa.int64()
            ),
        }
    )
    pq.write_table(table, path)
