"""Market data query API (Phase 1 — Data Platform).

Read-only endpoints over :class:`MarketDataRepository`. ``as_of`` and
``dataset_version`` are **required** on every data endpoint: the API cannot
accidentally serve "the latest" data to a simulated context, which is what
makes future information impossible to retrieve through the normal query API
(INV-3, Phase 1 DoD).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from adapters.market_data.catalog import Catalog, PostgresCatalog
from adapters.market_data.errors import (
    DatasetNotFoundError,
    DatasetNotSealedError,
    FutureDataLeakageError,
    MarketDataError,
)
from adapters.market_data.hashing import snapshot_data_hash
from adapters.market_data.repository import MarketDataRepository
from adapters.market_data.storage import MinioLayerStore
from core.clock.clocks import Clock
from core.config.settings import Settings
from core.domain.enums import Timeframe
from core.observability.metrics import OperationalMetrics, metrics
from core.schemas.base import ensure_utc
from fastapi import APIRouter, HTTPException, Query, status

__all__ = ["build_default_repository", "build_market_data_router"]


def build_default_repository(settings: Settings) -> tuple[MarketDataRepository, Catalog]:
    """Default Phase 1 wiring: MinIO + Parquet storage, PostgreSQL catalog.

    Construction performs no network I/O, so the API can build it at startup
    even when the local stack is down (requests then fail with 503/500).
    """
    store = MinioLayerStore(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    catalog = PostgresCatalog(settings.postgres_dsn)
    return MarketDataRepository(store, catalog), catalog


def _as_of_or_422(raw: datetime) -> datetime:
    try:
        return ensure_utc(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="timestamps must be timezone-aware (e.g. 2026-01-05T10:00:00+00:00)",
        ) from exc


def build_market_data_router(
    repository: MarketDataRepository,
    catalog: Catalog,
    clock: Clock,
    operational_metrics: OperationalMetrics | None = None,
) -> APIRouter:
    telemetry = operational_metrics or metrics
    router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])

    @router.get("/instruments")
    def list_instruments() -> dict[str, object]:
        return {"instruments": [i.canonical_dict() for i in catalog.list_instruments()]}

    @router.get("/bars")
    def get_bars(
        instrument_id: Annotated[str, Query(min_length=1)],
        as_of: Annotated[datetime, Query(description="explicit point-in-time anchor (required)")],
        dataset_version: Annotated[
            int, Query(ge=1, description="sealed gold dataset version (required)")
        ],
        timeframe: Timeframe,
        start: Annotated[datetime | None, Query()] = None,
        end: Annotated[datetime | None, Query()] = None,
    ) -> dict[str, object]:
        as_of_utc = _as_of_or_422(as_of)
        start_utc = _as_of_or_422(start) if start is not None else None
        end_utc = _as_of_or_422(end) if end is not None else None
        try:
            bars = repository.bars(
                instrument_id=instrument_id,
                timeframe=timeframe,
                as_of=as_of_utc,
                dataset_version=dataset_version,
                start=start_utc,
                end=end_utc,
            )
        except DatasetNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except DatasetNotSealedError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except FutureDataLeakageError:
            raise  # 500: evidence of an INV-3 bypass, must not be silenced
        except MarketDataError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe.value,
            "as_of": as_of_utc.isoformat(),
            "dataset_version": dataset_version,
            "count": len(bars),
            "bars": [bar.canonical_dict() for bar in bars],
        }

    @router.get("/snapshots/{instrument_id}")
    def get_snapshot(
        instrument_id: str,
        as_of: Annotated[datetime, Query(description="explicit point-in-time anchor (required)")],
        dataset_version: Annotated[
            int, Query(ge=1, description="sealed gold dataset version (required)")
        ],
        timeframe: Timeframe,
    ) -> dict[str, object]:
        as_of_utc = _as_of_or_422(as_of)
        try:
            snapshot = repository.snapshot(
                instrument_id=instrument_id,
                timeframe=timeframe,
                as_of=as_of_utc,
                dataset_version=dataset_version,
                clock=clock,
            )
        except DatasetNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except DatasetNotSealedError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except FutureDataLeakageError:
            raise  # 500: evidence of an INV-3 bypass, must not be silenced
        except MarketDataError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no bar visible at as_of={as_of_utc.isoformat()} "
                f"for {instrument_id}/{timeframe.value} v{dataset_version}",
            )
        telemetry.set_market_data_age(
            "repository", (clock.now() - snapshot.source_timestamp).total_seconds()
        )
        telemetry.set_market_data_timestamp("repository", snapshot.source_timestamp.timestamp())
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe.value,
            "as_of": as_of_utc.isoformat(),
            "dataset_version": dataset_version,
            "snapshot": snapshot.canonical_dict(),
            "snapshot_hash": snapshot_data_hash(snapshot),
        }

    return router
