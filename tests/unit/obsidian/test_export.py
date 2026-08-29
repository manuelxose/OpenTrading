from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from adapters.obsidian import MemoryVaultWriter
from adapters.obsidian.export import (
    REQUIRED_VAULT_DIRECTORIES,
    MirroringEventBus,
    ObsidianExporter,
    SecretDetectedError,
    initialize_vault,
)
from core.clock.clocks import VirtualClock
from core.events.envelope import build_domain_event

from factories import (
    make_experiment_run,
    make_posttrade_review,
    make_research_packet,
    make_safe_mode_event,
    make_strategy_candidate,
    make_trade_outcome,
)

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
TRACE_ID = UUID("11111111-1111-4111-8111-111111111111")


def _event(name: str, payload: object):
    return build_domain_event(
        event_name=name,
        payload=payload,  # type: ignore[arg-type]
        clock=VirtualClock(NOW),
        producer="tests.obsidian",
        trace_id=TRACE_ID,
    )


def test_initialize_vault_creates_the_canonical_layout(tmp_path) -> None:
    initialize_vault(tmp_path)
    assert {path.name for path in tmp_path.iterdir() if path.is_dir()} == set(
        REQUIRED_VAULT_DIRECTORIES
    )


@pytest.mark.parametrize(
    ("event_name", "payload", "prefix", "canonical_key"),
    [
        ("trade.closed", make_trade_outcome(NOW), "40_Trades/2026/EURUSD/", "trade_id"),
        (
            "postmortem.completed",
            make_posttrade_review(NOW),
            "50_Postmortems/2026/",
            "review_id",
        ),
        (
            "strategy.candidate.created",
            make_strategy_candidate(NOW),
            "10_Strategies/",
            "candidate_id",
        ),
        (
            "experiment.completed",
            make_experiment_run(
                NOW,
                status="COMPLETED",
                finished_at=NOW,
            ),
            "80_Experiments/2026/",
            "experiment_id",
        ),
        (
            "system.safe_mode.entered",
            make_safe_mode_event(NOW),
            "60_Risk/2026/",
            "event_id",
        ),
        (
            "research.completed",
            make_research_packet(NOW, confidence=0.9),
            "20_Research/2026/",
            "packet_id",
        ),
    ],
)
def test_export_event_writes_marked_note_with_canonical_and_trace_ids(
    event_name: str, payload: object, prefix: str, canonical_key: str
) -> None:
    writer = MemoryVaultWriter()
    exporter = ObsidianExporter(writer)
    event = _event(event_name, payload)

    path = exporter.export_event(event)

    assert path is not None and path.startswith(prefix)
    content = writer.note(path)
    assert content is not None
    assert "generated: true" in content
    assert "authoritative: false" in content
    assert f"trace_id: {TRACE_ID}" in content
    assert f"canonical_id_type: {canonical_key}" in content
    assert "AUTOMATICALLY GENERATED" in content


def test_low_confidence_research_is_not_exported() -> None:
    writer = MemoryVaultWriter()
    event = _event("research.completed", make_research_packet(NOW, confidence=0.79))
    assert ObsidianExporter(writer).export_event(event) is None
    assert writer.notes() == {}


def test_secret_like_content_is_rejected_before_write() -> None:
    writer = MemoryVaultWriter()
    payload = make_research_packet(NOW, confidence=0.9, findings=["api_key=super-secret-value"])
    with pytest.raises(SecretDetectedError):
        ObsidianExporter(writer).export_event(_event("research.completed", payload))
    assert writer.notes() == {}


def test_generic_token_field_is_rejected_before_write() -> None:
    writer = MemoryVaultWriter()
    payload = make_experiment_run(NOW, config={"token": "abcdefghijk12345"})
    with pytest.raises(SecretDetectedError):
        ObsidianExporter(writer).export_event(_event("experiment.created", payload))
    assert writer.notes() == {}


class _Bus:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):
        self.events.append(event)
        return "1-0"

    def pending(self):
        return "delegated"


class _BrokenExporter:
    def export_event(self, event):
        raise OSError("vault unavailable")


def test_mirror_failure_never_blocks_authoritative_publish() -> None:
    bus = _Bus()
    mirror = MirroringEventBus(bus, _BrokenExporter())  # type: ignore[arg-type]
    event = _event("trade.closed", make_trade_outcome(NOW))
    assert mirror.publish(event) == "1-0"
    assert bus.events == [event]
    assert mirror.pending() == "delegated"
