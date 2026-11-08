from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from samay.engine.errors import NonexistentTime
from samay.engine.geo import Place
from samay.engine.timestd import AmbiguousTime, TimeResolution, load_standards, resolve_local_time

FIXTURES = Path(__file__).parent / "fixtures" / "time_standards"
PUNE = Place("1259229", "Pune", "IN", "16", None, 18.52, 73.86, "Asia/Kolkata", 3124458)
NEW_YORK = Place("5128581", "New York City", "US", "NY", None, 40.71, -74.01, "America/New_York", 8804190)
CHICAGO = Place("4887398", "Chicago", "US", "IL", None, 41.85, -87.65, "America/Chicago", 2746388)
NONE: tuple = ()


def test_ist_after_1970():
    r = resolve_local_time(datetime(1990, 8, 15, 14, 30), PUNE, entries=NONE)
    assert isinstance(r, TimeResolution)
    assert r.utc == datetime(1990, 8, 15, 9, 0, tzinfo=timezone.utc)
    assert r.offset == timedelta(hours=5, minutes=30)
    assert r.confidence == "tzdata" and r.warning is None
    assert "UTC+05:30" in r.source


def test_historical_us_dst():
    r = resolve_local_time(datetime(1990, 7, 1, 12, 0), CHICAGO, entries=NONE)
    assert r.utc.hour == 17


def test_pre_1956_india_is_low_confidence_with_warning():
    r = resolve_local_time(datetime(1952, 8, 5, 6, 0), PUNE, entries=NONE)
    assert r.confidence == "low"
    assert "Bombay Time" in r.warning


def test_ambiguous_dst_overlap():
    r = resolve_local_time(datetime(2021, 11, 7, 1, 30), NEW_YORK, entries=NONE)
    assert isinstance(r, AmbiguousTime)
    first, second = r.options
    assert second - first == timedelta(hours=1)
    assert resolve_local_time(datetime(2021, 11, 7, 1, 30), NEW_YORK, fold=0, entries=NONE).utc == first
    assert resolve_local_time(datetime(2021, 11, 7, 1, 30), NEW_YORK, fold=1, entries=NONE).utc == second


def test_nonexistent_dst_gap():
    with pytest.raises(NonexistentTime):
        resolve_local_time(datetime(2021, 3, 14, 2, 30), NEW_YORK, entries=NONE)


def test_curated_entry_overrides_tzdata():
    entries = load_standards(FIXTURES)
    r = resolve_local_time(datetime(1952, 8, 5, 6, 0), PUNE, entries=entries)
    assert r.offset == timedelta(hours=4, minutes=51)
    assert r.utc == datetime(1952, 8, 5, 1, 9, tzinfo=timezone.utc)
    assert r.confidence == "probable" and "Test fixture" in r.source and r.warning is None


def test_curated_entry_limited_to_its_region_and_dates():
    entries = load_standards(FIXTURES)
    other_state = Place("1", "Kolkata", "IN", "28", None, 22.57, 88.36, "Asia/Kolkata", 1)
    assert resolve_local_time(datetime(1952, 8, 5, 6, 0), other_state, entries=entries).confidence == "low"
    assert resolve_local_time(datetime(1960, 1, 1, 6, 0), PUNE, entries=entries).confidence == "low"


def test_malformed_entry_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text("- {country: IN, from: 1950-01-01}\n")
    with pytest.raises(ValueError, match="missing"):
        load_standards(tmp_path)


def test_shipped_tables_load():
    load_standards()
