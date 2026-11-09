"""Sunrise, sunset and Rahu Kaala for a place and a local calendar day, computed offline.

Sunrise and sunset use the usual definition (upper edge of the Sun on the horizon, with standard
refraction), from the same JPL kernel as the charts. Rahu Kaala is one eighth of the daytime
(sunrise to sunset); which eighth depends on the weekday. The order below is the one published
calculators agree on (checked 2026-11-09 against several, and against a published New Delhi
figure; see tests/fixtures/rahu_kaala_published.yaml). It is not yet checked against a primary
text, so it carries no citation to one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from skyfield import almanac
from skyfield.api import wgs84

from . import ephemeris

# Weekday (Monday = 0) -> which eighth of the daytime, counting from sunrise.
RAHU_KAALA_PART = {0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3, 6: 8}
PARTS = 8


@dataclass(frozen=True)
class SunTimes:
    sunrise: datetime  # timezone-aware, in the place's own zone
    sunset: datetime


@dataclass(frozen=True)
class RahuKaala:
    day: date
    start: datetime
    end: datetime
    sunrise: datetime
    sunset: datetime


def sun_times(latitude: float, longitude: float, tz: str, day: date) -> SunTimes | None:
    """Sunrise and sunset on a local calendar day, or None when the Sun does not both rise and set
    that day (polar summer and winter)."""
    zone = ZoneInfo(tz)
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    ts = ephemeris._timescale()
    is_up = almanac.sunrise_sunset(ephemeris._kernel(), wgs84.latlon(latitude, longitude))
    times, events = almanac.find_discrete(
        ts.from_datetime(start.astimezone(UTC)), ts.from_datetime((start + timedelta(days=1)).astimezone(UTC)), is_up
    )
    rises = [t.utc_datetime().astimezone(zone) for t, up in zip(times, events, strict=True) if up]
    sets = [t.utc_datetime().astimezone(zone) for t, up in zip(times, events, strict=True) if not up]
    if not rises or not sets:
        return None
    sunrise = rises[0]
    after = [s for s in sets if s > sunrise]
    return SunTimes(sunrise, after[0]) if after else None


def rahu_kaala(latitude: float, longitude: float, tz: str, day: date) -> RahuKaala | None:
    sun = sun_times(latitude, longitude, tz, day)
    if sun is None:
        return None
    part = (sun.sunset - sun.sunrise) / PARTS
    index = RAHU_KAALA_PART[day.weekday()] - 1
    start = sun.sunrise + part * index
    return RahuKaala(day, start, start + part, sun.sunrise, sun.sunset)
