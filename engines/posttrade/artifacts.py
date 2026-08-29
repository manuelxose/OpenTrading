"""Post-trade artifacts: full audit payloads in MinIO (INV-10).

PostgreSQL stores the canonical, typed metrics; MinIO stores the *heavy*
immutable artifact — the complete review payload, the captured trade context
and the observed price path — under a deterministic key, so the same trade
always lands on the same object (replay-safe).
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from core.schemas.posttrade import PostTradeReviewRecord

__all__ = [
    "ArtifactStore",
    "MemoryArtifactStore",
    "MinioArtifactStore",
    "artifact_key",
    "build_artifact",
]


class ArtifactStore(Protocol):
    """Object-storage boundary for post-trade artifacts."""

    def put_json(self, key: str, payload: dict[str, Any]) -> None: ...
    def get_json(self, key: str) -> dict[str, Any]: ...
    def exists(self, key: str) -> bool: ...


def artifact_key(closed_at: datetime, review_id: UUID) -> str:
    """Deterministic object key: ``reviews/<year>/<month>/<review_id>.json``."""
    return f"reviews/{closed_at.year:04d}/{closed_at.month:02d}/{review_id}.json"


def build_artifact(
    record: PostTradeReviewRecord,
    context_fragments: dict[str, Any],
    price_path: list[dict[str, Any]],
) -> dict[str, Any]:
    """The immutable audit artifact for one review.

    Canonical payloads are embedded in JSON mode (UUIDs and Decimals as
    strings), so the artifact deserializes losslessly back into contracts.
    """
    return {
        "artifact_schema": "opentrading.posttrade.artifact",
        "artifact_schema_version": "1.0.0",
        "review": record.review_payload,
        "metrics": record.metrics.model_dump(mode="json"),
        "trade_context": context_fragments,
        "price_path": list(price_path),
    }


class MemoryArtifactStore:
    """Deterministic in-memory store (unit tests, dev)."""

    def __init__(self) -> None:
        self._objects: dict[str, dict[str, Any]] = {}

    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        self._objects[key] = json.loads(json.dumps(payload, default=str))

    def get_json(self, key: str) -> dict[str, Any]:
        return dict(self._objects[key])

    def exists(self, key: str) -> bool:
        return key in self._objects


class MinioArtifactStore:
    """S3-compatible artifact storage backed by MinIO (ADR-0011)."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        *,
        bucket: str,
        secure: bool = False,
    ) -> None:
        from minio import Minio  # local import keeps core import-light

        self._bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        self._ensure_bucket()
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._client.put_object(self._bucket, key, io.BytesIO(data), length=len(data))

    def get_json(self, key: str) -> dict[str, Any]:
        response = None
        try:
            response = self._client.get_object(self._bucket, key)
            value = json.loads(response.read().decode("utf-8"))
            return dict(value)
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def exists(self, key: str) -> bool:
        try:
            self._client.stat_object(self._bucket, key)
            return True
        except Exception:
            return False
