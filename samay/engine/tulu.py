"""The Tulu solar calendar: the month is the Sun's sidereal sign, counted from its entry (sankramana).

Which civil day is day 1 when the Sun enters a sign late in the day is disputed between calendars, so it is a profile
choice (`sankranti_cutoff`), never counted naively: same_day, sunset (before local sunset), aparahna (before 60% of the
daytime has passed) or next_day. The names of these options do not claim a tradition; the family's own anchors decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import daylight, ephemeris
from .errors import UnknownProfile
from .paths import PROFILES_DIR

MONTHS = (
    "Paggu",
    "Besha",
    "Kaarthel",
    "Aati",
    "Sona",
    "Nirnala",
    "Bonthel",
    "Jarde",
    "Perarde",
    "Puyintel",
    "Maayi",
    "Suggi",
)
CUTOFFS = ("same_day", "sunset", "aparahna", "next_day")
APARAHNA_FRACTION = 0.6
LOOKBACK = timedelta(days=33)  # longer than any solar month


@dataclass(frozen=True)
class TuluProfile:
    ayanamsa: str
    cutoff: str


@dataclass(frozen=True)
class TuluDate:
    month: str
    day: int
    ingress: datetime  # when the Sun entered this month's sign, local
    month_starts: date  # the civil day the cutoff rule calls day 1


@lru_cache(maxsize=2)
def load_tulu_profile(directory: Path = PROFILES_DIR) -> TuluProfile:
    path = directory / "tulu.yaml"
    if not path.is_file():
        raise UnknownProfile("missing tulu profile")
    raw = yaml.safe_load(path.read_text())
    if raw["sankranti_cutoff"] not in CUTOFFS:
        raise ValueError(f"profile field 'sankranti_cutoff': unsupported value {raw['sankranti_cutoff']!r}")
    if raw["ayanamsa"] not in ephemeris.AYANAMSAS:
        raise ValueError(f"profile field 'ayanamsa': unsupported value {raw['ayanamsa']!r}")
    return TuluProfile(raw["ayanamsa"], raw["sankranti_cutoff"])


def _sun(utc: datetime, ayanamsa: str) -> float:
    return ephemeris.sidereal_track([utc], ayanamsa)["sun"][0]


def last_ingress(utc: datetime, ayanamsa: str = "lahiri_mean") -> tuple[int, datetime]:
    """(sign index 0-11, UTC instant) of the most recent time the Sun entered the sidereal sign it is in at `utc`."""
    sign = int(_sun(utc, ayanamsa) // 30) % 12
    target = sign * 30.0

    def reached(t: datetime) -> bool:
        return (((_sun(t, ayanamsa) - target) + 180.0) % 360.0) - 180.0 >= 0.0

    inside, outside = utc, utc - LOOKBACK  # reached(inside) is True, reached(outside) is False
    while inside - outside > timedelta(seconds=1):
        mid = outside + (inside - outside) / 2
        if reached(mid):
            inside = mid
        else:
            outside = mid
    return sign, inside


def month_start(ingress: datetime, latitude: float, longitude: float, tz: str, cutoff: str) -> date:
    """The civil day that counts as day 1 of the month the Sun entered at `ingress`."""
    local = ingress.astimezone(ZoneInfo(tz))
    day = local.date()
    if cutoff == "same_day":
        return day
    if cutoff == "next_day":
        return day + timedelta(days=1)
    sun = daylight.sun_times(latitude, longitude, tz, day)
    if sun is None:
        return day
    limit = sun.sunset if cutoff == "sunset" else sun.sunrise + (sun.sunset - sun.sunrise) * APARAHNA_FRACTION
    return day if local < limit else day + timedelta(days=1)


def tulu_date(
    day: date, latitude: float, longitude: float, tz: str, cutoff: str, ayanamsa: str = "lahiri_mean"
) -> TuluDate:
    if cutoff not in CUTOFFS:
        raise ValueError(f"unknown sankranti cutoff {cutoff!r}")
    zone = ZoneInfo(tz)
    day_end = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(UTC) + timedelta(days=1)
    sign, ingress = last_ingress(day_end - timedelta(seconds=1), ayanamsa)
    start = month_start(ingress, latitude, longitude, tz, cutoff)
    if start > day:  # the Sun entered the sign today but the cutoff makes the month start tomorrow
        sign, ingress = last_ingress(ingress - timedelta(seconds=1), ayanamsa)
        start = month_start(ingress, latitude, longitude, tz, cutoff)
    return TuluDate(MONTHS[sign], (day - start).days + 1, ingress.astimezone(zone), start)
