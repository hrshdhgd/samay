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


@pytest.mark.parametrize("date_text,time_text", [("1990-13-40", "14:30"), ("1990-08-15", "2pm")])
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
