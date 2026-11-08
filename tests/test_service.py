from datetime import UTC, datetime, timedelta

import pytest

from samay import service
from samay.engine.errors import InvalidInput, PlaceNotFound, UnknownProfile
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput, NeedsDisambiguation, ResolvedBirth

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE_1990 = BirthInput("1990-08-15", "14:30", "Pune")


def test_resolve_with_provenance():
    b = service.resolve_birth(PUNE_1990)
    assert isinstance(b, ResolvedBirth)
    assert b.utc == datetime(1990, 8, 15, 9, 0, tzinfo=UTC)
    assert b.provenance.offset == timedelta(hours=5, minutes=30)
    assert b.provenance.confidence == "tzdata"


def test_day_first_date_accepted():
    assert service.resolve_birth(BirthInput("15-08-1990", "14:30", "Pune")).utc.hour == 9


def test_place_disambiguation_then_choice():
    d = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Springfield, US"))
    assert isinstance(d, NeedsDisambiguation) and d.kind == "place" and len(d.options) == 3
    chosen = d.options[1]
    b = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Springfield, US", place_choice=chosen.id))
    assert b.place == chosen


def test_time_disambiguation():
    d = service.resolve_birth(BirthInput("2021-11-07", "01:30", "New York City"))
    assert isinstance(d, NeedsDisambiguation) and d.kind == "time"
    b = service.resolve_birth(BirthInput("2021-11-07", "01:30", "New York City", fold=1))
    assert b.utc == d.options[1]


@pytest.mark.parametrize("date_text,time_text", [("1990-13-40", "14:30"), ("1990-08-15", "25:61"), ("1990-08-15", "13pm")])
def test_bad_input(date_text, time_text):
    with pytest.raises(InvalidInput):
        service.resolve_birth(BirthInput(date_text, time_text, "Pune"))


def test_unknown_place_and_profile():
    with pytest.raises(PlaceNotFound):
        service.resolve_birth(BirthInput("1990-08-15", "14:30", "Nowhereville"))
    with pytest.raises(UnknownProfile):
        service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune", profile="nope"))


@needs_kernel
def test_natal_report_is_stamped_unvalidated_and_cached():
    b = service.resolve_birth(PUNE_1990)
    service.natal_report.cache_clear()
    r = service.natal_report(b)
    assert r.validated is False
    assert r.stamp.profile_id == "parashari-lahiri"
    assert r.stamp.ephemeris.startswith("de440s ")
    assert len(r.dashas) == 9
    assert service.natal_report(b) is r
    assert service.natal_report.cache_info().hits == 1


@needs_kernel
def test_today_report_uses_injected_now():
    b = service.resolve_birth(PUNE_1990)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    t = service.today_report(b, now)
    assert t.now == now and t.sky.utc == now
    assert dict(t.transit_houses).keys() == {"jupiter", "saturn", "rahu", "ketu"}
    assert t.current_dasha is not None


@needs_kernel
def test_warm_returns_stamp():
    assert service.warm().profile_id == "parashari-lahiri"


def test_nearby_town_is_flagged_approximate():
    b = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune", approx_for="Wagholi"))
    assert b.provenance.place_approximate
    assert "Wagholi" in b.provenance.approx_note and "Pune" in b.provenance.approx_note
    assert not service.resolve_birth(PUNE_1990).provenance.place_approximate


@pytest.mark.parametrize(
    "text",
    ["1952-08-15", "15-08-1952", "15/8/1952", "15.08.1952", "15 August 1952", "15th Aug 1952", "August 15, 1952"],
)
def test_friendly_dates(text):
    assert service.parse_date(text) == datetime(1952, 8, 15)


@pytest.mark.parametrize(
    "text,hour,minute,ambiguous",
    [
        ("6:30", 6, 30, True), ("6.30", 6, 30, True), ("6", 6, 0, True), ("12:15", 12, 15, True),
        ("6:30 am", 6, 30, False), ("6:30PM", 18, 30, False), ("6pm", 18, 0, False),
        ("12 am", 0, 0, False), ("12:30 pm", 12, 30, False), ("18:30", 18, 30, False), ("0:45", 0, 45, False),
    ],
)
def test_friendly_clock(text, hour, minute, ambiguous):
    assert service.parse_clock(text) == service.Clock(hour, minute, ambiguous)
