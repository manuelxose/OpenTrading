"""Best-effort Obsidian mirror of authoritative domain events.

The event bus and canonical stores remain authoritative.  This module only
produces human-readable Markdown and deliberately swallows mirror failures at
the publisher boundary so vault availability can never gate trading.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.schemas.events import DomainEvent

from .vault import VaultWriter

__all__ = [
    "REQUIRED_VAULT_DIRECTORIES",
    "MirroringEventBus",
    "ObsidianExporter",
    "SecretDetectedError",
    "ensure_secret_free",
    "initialize_vault",
]

logger = logging.getLogger(__name__)

REQUIRED_VAULT_DIRECTORIES = (
    "00_System",
    "10_Strategies",
    "20_Research",
    "30_Market",
    "40_Trades",
    "50_Postmortems",
    "60_Risk",
    "70_Agents",
    "80_Experiments",
    "90_Auto",
)

_EVENT_KINDS = {
    "trade.closed": "trade",
    "postmortem.completed": "postmortem",
    "strategy.candidate.created": "strategy",
    "strategy.promoted": "strategy",
    "strategy.retired": "strategy",
    "experiment.created": "experiment",
    "experiment.completed": "experiment",
    "reconciliation.divergence": "risk_incident",
    "system.safe_mode.entered": "risk_incident",
    "research.completed": "research_conclusion",
}

_CANONICAL_IDS = {
    "trade": ("trade_id",),
    "postmortem": ("review_id", "trade_id"),
    "strategy": ("candidate_id", "strategy_candidate_id", "decision_id"),
    "experiment": ("experiment_id",),
    "risk_incident": ("run_id",),
    "research_conclusion": ("packet_id",),
}

_SECRET_KEY = re.compile(
    r"(?:(?:^|[_-])token(?:$|[_-])|api[_-]?key|password|passwd|secret|"
    r"access[_-]?token|refresh[_-]?token|"
    r"broker[_-]?(?:credential|password)|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\b(?:api[_-]?key|password|passwd|secret|token)\s*[:=]\s*[^\s,;]{8,})",
    re.IGNORECASE,
)


class SecretDetectedError(ValueError):
    """Raised when content looks like credential material and is not written."""


def initialize_vault(base_dir: str | Path) -> None:
    """Create the canonical vault directory topology without touching data stores."""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    for directory in REQUIRED_VAULT_DIRECTORIES:
        (base / directory).mkdir(exist_ok=True)


class ObsidianExporter:
    """Render selected canonical events into deterministic Markdown notes."""

    def __init__(
        self,
        writer: VaultWriter,
        *,
        important_research_min_confidence: float = 0.8,
    ) -> None:
        self._writer = writer
        self._research_threshold = important_research_min_confidence

    def export_event(self, event: DomainEvent) -> str | None:
        """Write a mirror note when ``event`` is exportable; otherwise return ``None``."""
        kind = _EVENT_KINDS.get(event.event_name)
        if kind is None:
            return None
        if kind == "postmortem" and event.payload.get("vault_path"):
            # The post-trade engine writes a richer note before emitting this
            # event. Preserve that canonical mirror instead of duplicating it.
            return str(event.payload["vault_path"])
        if (
            kind == "research_conclusion"
            and float(event.payload.get("confidence", 0)) < self._research_threshold
        ):
            return None

        canonical_type, canonical_id = _canonical_id(kind, event)
        path = _note_path(kind, event, canonical_id)
        content = _render(kind, event, canonical_type, canonical_id)
        ensure_secret_free(event.payload, content)
        return self._writer.write_note(path, content)


class MirroringEventBus:
    """Bus proxy that mirrors only after authoritative publish succeeds.

    Export errors are logged by type and never propagated. All non-publish bus
    operations are delegated unchanged.
    """

    def __init__(self, bus: Any, exporter: ObsidianExporter) -> None:
        self._bus = bus
        self._exporter = exporter

    @property
    def raw_bus(self) -> Any:
        return self._bus

    def publish(self, event: DomainEvent) -> str:
        message_id = str(self._bus.publish(event))
        self.mirror_only(event)
        return message_id

    def mirror_only(self, event: DomainEvent) -> None:
        """Mirror an already-authoritative event (used by synchronous runs)."""
        try:
            self._exporter.export_event(event)
        except Exception as exc:
            logger.warning(
                "obsidian mirror failed for event %s: %s",
                event.event_id,
                type(exc).__name__,
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bus, name)


def _canonical_id(kind: str, event: DomainEvent) -> tuple[str, str]:
    for key in _CANONICAL_IDS[kind]:
        value = event.payload.get(key)
        if value:
            return key, str(value)
    return "event_id", str(event.event_id)


def _note_path(kind: str, event: DomainEvent, canonical_id: str) -> str:
    year = event.event_time.year
    safe_id = _slug(canonical_id)
    if kind == "trade":
        instrument = _slug(str(event.payload.get("instrument_id", "unknown")))
        return f"40_Trades/{year}/{instrument}/{safe_id}.md"
    roots = {
        "postmortem": "50_Postmortems",
        "strategy": "10_Strategies",
        "experiment": "80_Experiments",
        "risk_incident": "60_Risk",
        "research_conclusion": "20_Research",
    }
    root = roots[kind]
    if kind == "strategy":
        return f"{root}/{safe_id}-{event.event_id.hex[:8]}.md"
    return f"{root}/{year}/{event.event_time:%Y-%m-%d}-{safe_id}.md"


def _render(
    kind: str,
    event: DomainEvent,
    canonical_type: str,
    canonical_id: str,
) -> str:
    title = kind.replace("_", " ").title()
    trace_id = str(event.trace_id) if event.trace_id is not None else "null"
    lines = [
        "---",
        "generated: true",
        "authoritative: false",
        "generator: OpenTrading Obsidian export",
        f"note_type: {kind}",
        f"canonical_id_type: {canonical_type}",
        f"canonical_id: {_yaml_scalar(canonical_id)}",
        f"event_id: {event.event_id}",
        f"trace_id: {trace_id}",
        f"event_name: {event.event_name}",
        f"event_time: {event.event_time.isoformat()}",
        "---",
        "",
        f"# {title} — {canonical_id}",
        "",
        "> [!WARNING] AUTOMATICALLY GENERATED MIRROR",
        (
            "> This note is for human inspection only. Canonical trading data "
            "lives in the platform stores."
        ),
        "",
        "## Summary",
        "",
    ]
    lines.extend(_summary_lines(kind, event.payload))
    lines.extend(
        [
            "",
            "## Canonical event snapshot",
            "",
            "```json",
            json.dumps(event.payload, indent=2, sort_keys=True, ensure_ascii=False, default=str),
            "```",
            "",
            "## Trace",
            "",
            f"- Event: `{event.event_id}`",
            f"- Trace: `{trace_id}`",
            f"- Producer: `{event.producer}`",
            "",
        ]
    )
    return "\n".join(lines)


def _summary_lines(kind: str, payload: dict[str, Any]) -> list[str]:
    fields = {
        "trade": ("instrument_id", "direction", "realized_pnl", "r_multiple", "exit_reason"),
        "postmortem": ("trade_id", "postmortem_completed", "lessons"),
        "strategy": ("name", "state", "from_state", "to_state", "decision"),
        "experiment": ("name", "experiment_type", "status", "metrics"),
        "risk_incident": ("active", "reason_codes", "material_discrepancies", "discrepancy_codes"),
        "research_conclusion": ("summary", "findings", "confidence", "related_instruments"),
    }[kind]
    result = []
    for field in fields:
        if field in payload and payload[field] not in (None, [], {}):
            value = json.dumps(payload[field], ensure_ascii=False, default=str)
            result.append(f"- **{field.replace('_', ' ').title()}:** {value}")
    return result or ["- No summary fields were present in the canonical event."]


def ensure_secret_free(payload: dict[str, Any], rendered: str) -> None:
    """Reject secret-like keys or credential values before a vault write."""

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if _SECRET_KEY.search(str(key)):
                    raise SecretDetectedError("secret-like field name detected")
                walk(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)
        elif isinstance(value, str) and _SECRET_VALUE.search(value):
            raise SecretDetectedError("secret-like value detected")

    walk(payload)
    if _SECRET_VALUE.search(rendered):
        raise SecretDetectedError("secret-like rendered content detected")


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return slug[:120] or "unknown"


def _yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
