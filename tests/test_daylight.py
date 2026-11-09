import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from samay.engine import daylight
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden_suntimes.json").read_text())["cases"]
PUBLISHED = yaml.safe_load((FIXTURES / "rahu_kaala_published.yaml").read_text())
SUN_TOLERANCE = timedelta(seconds=15)  # Skyfield and Swiss Ephemeris differ by up to ~6 s


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_sunrise_and_sunset_match_swiss_ephemeris(case):
    sun = daylight.sun_times(case["latitude"], case["longitude"], case["tz"], date.fromisoformat(case["date"]))
    assert abs(sun.sunrise - datetime.fromisoformat(case["sunrise"])) < SUN_TOLERANCE
    assert abs(sun.sunset - datetime.fromisoformat(case["sunset"])) < SUN_TOLERANCE


@pytest.mark.parametrize("p", PUBLISHED, ids=[p["place"] for p in PUBLISHED])
def test_matches_published_figures_to_the_minute(p):
    r = daylight.rahu_kaala(p["latitude"], p["longitude"], p["tz"], p["date"])
    minute = timedelta(minutes=1)

    def at(text: str) -> datetime:
        return datetime.combine(p["date"], datetime.strptime(text, "%H:%M").time(), tzinfo=r.sunrise.tzinfo)

    assert abs(r.sunrise - at(p["sunrise"])) <= minute
    assert abs(r.start - at(p["rahu_kaala"][0])) <= minute and abs(r.end - at(p["rahu_kaala"][1])) <= minute


def test_weekday_table_is_the_published_order():
    assert daylight.RAHU_KAALA_PART == {0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3, 6: 8}  # Mon..Sun


def test_each_weekday_uses_its_own_eighth_of_the_daytime():
    week = [daylight.rahu_kaala(18.5196, 73.8553, "Asia/Kolkata", date(2026, 11, 9) + timedelta(days=i)) for i in range(7)]
    for r in week:
        part = (r.sunset - r.sunrise) / 8
        assert r.end - r.start == part
        assert r.start == r.sunrise + part * (daylight.RAHU_KAALA_PART[r.day.weekday()] - 1)
        assert r.sunrise < r.start < r.end <= r.sunset
    assert len({r.start.strftime("%H:%M") for r in week}) > 1
    assert all(r.start != r.sunrise for r in week)  # never the first part


def test_dst_zone_gives_local_wall_clock_times():
    summer = daylight.rahu_kaala(44.953, -93.023, "America/Chicago", date(2026, 7, 6))
    winter = daylight.rahu_kaala(44.953, -93.023, "America/Chicago", date(2026, 1, 5))
    assert summer.sunrise.utcoffset() == timedelta(hours=-5) and winter.sunrise.utcoffset() == timedelta(hours=-6)
    assert 5 <= summer.sunrise.hour <= 6 and 7 <= winter.sunrise.hour <= 8


def test_no_sunrise_in_polar_winter_and_no_sunset_in_polar_summer():
    assert daylight.sun_times(69.65, 18.96, "Europe/Oslo", date(2026, 12, 21)) is None
    assert daylight.rahu_kaala(69.65, 18.96, "Europe/Oslo", date(2026, 6, 21)) is None
    assert daylight.sun_times(69.65, 18.96, "Europe/Oslo", date(2026, 3, 20)) is not None


def test_returns_timezone_aware_local_times():
    r = daylight.rahu_kaala(18.5196, 73.8553, "Asia/Kolkata", date(2026, 11, 9))
    assert r.start.utcoffset() == timedelta(hours=5, minutes=30)
    assert r.start.astimezone(UTC).tzinfo is UTC
