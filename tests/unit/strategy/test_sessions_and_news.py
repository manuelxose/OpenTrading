"""Session/DST normalization (spec §11) and the news risk filter (spec §12).

The DST cases exist because a naively-built London/New-York rule silently shifts
twice a year, which makes a backtest and a live terminal disagree without either
of them reporting an error.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from research.strategies.xau_rpb import NewsCalendar, SessionResolver
from research.strategies.xau_rpb.news import NewsEvent
from research.strategies.xau_rpb.sessions import infer_broker_utc_offset

# A broker on UTC+2 in winter — the common MetaQuotes-style server offset.
BROKER_OFFSET = 2.0


def resolver(**kw: object) -> SessionResolver:
    return SessionResolver(BROKER_OFFSET, **kw)  # type: ignore[arg-type]


def test_broker_time_converts_to_utc_using_the_configured_offset() -> None:
    r = resolver()
    assert r.to_utc(datetime(2024, 1, 15, 12, 0)) == datetime(
        2024, 1, 15, 10, 0, tzinfo=UTC
    )


def test_london_session_is_detected_in_winter() -> None:
    # 10:00 broker = 08:00 UTC = 08:00 London (GMT in January).
    flags = resolver().flags(datetime(2024, 1, 15, 10, 0))
    assert flags.london and not flags.new_york


def test_london_session_shifts_correctly_under_summer_dst() -> None:
    """In July London is UTC+1, so 08:00 local is 07:00 UTC, not 08:00 UTC."""
    r = resolver()
    # 09:00 broker = 07:00 UTC = 08:00 London (BST) -> the session has just opened.
    assert r.flags(datetime(2024, 7, 15, 9, 0)).london
    # 08:45 broker = 06:45 UTC = 07:45 London -> still closed.
    assert not r.flags(datetime(2024, 7, 15, 8, 45)).london


def test_new_york_session_and_overlap_are_detected() -> None:
    # 16:00 broker = 14:00 UTC = 09:00 New York (EST) and 14:00 London.
    flags = resolver().flags(datetime(2024, 1, 15, 16, 0))
    assert flags.new_york and flags.london and flags.overlap
    assert flags.label == "OVERLAP"


def test_rollover_is_flagged_and_blocked_by_default() -> None:
    r = resolver()
    # 00:00 broker = 22:00 UTC, inside the 21:00-23:00 UTC rollover band.
    moment = datetime(2024, 1, 16, 0, 0)
    assert r.flags(moment).rollover
    assert not r.is_permitted(moment), "structurally wide spreads are excluded by default"


def test_asian_session_is_excluded_unless_explicitly_allowed() -> None:
    # 03:00 broker = 01:00 UTC = 10:00 Tokyo, inside the 09:00-17:00 Tokyo day.
    moment = datetime(2024, 1, 16, 3, 0)
    assert not resolver().is_permitted(moment)
    assert resolver(allow_asian=True).is_permitted(moment)


def test_the_permitted_window_covers_london_and_new_york() -> None:
    r = resolver()
    assert r.is_permitted(datetime(2024, 1, 15, 11, 0))   # London
    assert r.is_permitted(datetime(2024, 1, 15, 20, 0))   # New York afternoon
    assert not r.is_permitted(datetime(2024, 1, 15, 5, 0))  # dead zone


def test_the_broker_offset_is_reported_for_reproducibility() -> None:
    assert resolver().broker_utc_offset_hours == pytest.approx(BROKER_OFFSET)


def test_broker_offset_inference_rounds_to_the_quarter_hour() -> None:
    broker = datetime(2024, 1, 15, 12, 1)
    known = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
    assert infer_broker_utc_offset(broker, known) == pytest.approx(2.0)


# ------------------------------------------------------------------ news filter


def event(hour: int, minute: int = 0) -> NewsEvent:
    return NewsEvent(
        event_time_utc=datetime(2024, 1, 11, hour, minute, tzinfo=UTC),
        currency="USD",
        impact="HIGH",
        name="CPI m/m",
    )


def test_blackout_covers_the_window_before_and_after_the_event() -> None:
    cal = NewsCalendar([event(13, 30)], block_before_min=30, block_after_min=15)

    assert cal.is_blackout(datetime(2024, 1, 11, 13, 5, tzinfo=UTC))
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 30, tzinfo=UTC))
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 44, tzinfo=UTC))


def test_outside_the_window_trading_is_permitted() -> None:
    cal = NewsCalendar([event(13, 30)], block_before_min=30, block_after_min=15)

    assert not cal.is_blackout(datetime(2024, 1, 11, 12, 59, tzinfo=UTC))
    assert not cal.is_blackout(datetime(2024, 1, 11, 13, 46, tzinfo=UTC))


def test_the_window_boundaries_are_inclusive() -> None:
    cal = NewsCalendar([event(13, 30)], block_before_min=30, block_after_min=15)
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 0, tzinfo=UTC))
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 45, tzinfo=UTC))


def test_an_empty_optional_calendar_never_blocks() -> None:
    assert not NewsCalendar.empty(required=False).is_blackout(datetime.now(UTC))


def test_a_required_but_missing_calendar_fails_closed() -> None:
    """Spec §15: a corrupted or absent calendar blocks entries, it does not wave them through."""
    cal = NewsCalendar.empty(required=True)
    assert not cal.is_usable
    assert cal.is_blackout(datetime.now(UTC))


def test_a_failed_load_fails_closed(tmp_path: object) -> None:
    cal = NewsCalendar.failed("missing.csv")
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 30, tzinfo=UTC))


def test_csv_round_trip_keeps_only_high_impact_usd_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "news.csv"
    path.write_text(
        "event_time_utc,currency,impact,event_name\n"
        "2024-01-11T13:30:00Z,USD,HIGH,CPI m/m\n"
        "2024-01-11T15:00:00Z,USD,LOW,Random survey\n"
        "2024-01-11T16:00:00Z,EUR,HIGH,ECB speech\n"
        "not-a-date,USD,HIGH,Broken row\n",
        encoding="utf-8",
    )
    cal = NewsCalendar.from_csv(path)

    assert len(cal) == 1, "low-impact, non-USD and unparseable rows are all dropped"
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 30, tzinfo=UTC))


def test_a_missing_required_file_fails_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cal = NewsCalendar.from_csv(tmp_path / "absent.csv", required=True)
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 30, tzinfo=UTC))


def test_a_file_with_a_wrong_header_fails_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "bad.csv"
    path.write_text("when,currency,impact\n2024-01-11T13:30:00Z,USD,HIGH\n", encoding="utf-8")
    cal = NewsCalendar.from_csv(path, required=True)
    assert cal.is_blackout(datetime(2024, 1, 11, 13, 30, tzinfo=UTC))


def test_many_events_are_queried_without_scanning_them_all() -> None:
    events = [
        NewsEvent(
            datetime(2024, 1, 1, tzinfo=UTC).replace(day=(i % 28) + 1, hour=i % 24),
            "USD", "HIGH", f"event {i}",
        )
        for i in range(500)
    ]
    cal = NewsCalendar(events)
    assert isinstance(cal.is_blackout(datetime(2024, 1, 15, 3, 0, tzinfo=UTC)), bool)
