"""The only API front ends call. Synchronous; the bot runs it in a worker thread."""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from .engine import daylight, ephemeris, geo, timestd
from .engine.daylight import RahuKaala
from .engine.errors import InvalidInput, PlaceNotFound
from .engine.geo import Place
from .engine.paths import EPHEMERIS_PATH, TIME_STANDARDS_DIR
from .engine.profiles import DEFAULT_PROFILE, load_profile
from .engine.rules import fired, load_rules, rules_hash
from .engine.vedic import current_dasha, house_from, sign_index, vimshottari
from .models import (
    BirthInput,
    NatalReport,
    NeedsDisambiguation,
    Provenance,
    ResolvedBirth,
    TodayReport,
    VersionStamp,
)

DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
)
TRANSIT_GRAHAS = ("jupiter", "saturn", "rahu", "ketu")
_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b", re.IGNORECASE)
_CLOCK = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:([ap])\.?\s*m\.?)?", re.IGNORECASE)


@dataclass(frozen=True)
class Clock:
    hour: int  # 24-hour reading of what was typed
    minute: int
    ambiguous: bool  # typed 1-12 with no am/pm, so the hour could mean morning or evening


def parse_date(text: str) -> datetime:
    """'1952-08-15', '15-08-1952', '15/8/1952', '15th August 1952', 'August 15, 1952'."""
    cleaned = " ".join(_ORDINAL.sub("", text.replace(",", " ")).split())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise InvalidInput(f"could not read the date {text!r}; use DD-MM-YYYY, e.g. 15-08-1952")


def parse_clock(text: str) -> Clock:
    """'6:30', '6.30', '6pm', '6:30 PM', '18:30'."""
    m = _CLOCK.fullmatch(text.strip())
    if not m:
        raise InvalidInput(f"could not read the time {text!r}; use HH:MM, e.g. 6:30 am")
    hour, minute, marker = int(m[1]), int(m[2] or 0), (m[3] or "").lower()
    if minute > 59 or hour > 23 or (marker and not 1 <= hour <= 12):
        raise InvalidInput(f"{text!r} is not a valid time")
    if marker:
        hour = hour % 12 + (12 if marker == "p" else 0)
    return Clock(hour, minute, ambiguous=not marker and 1 <= hour <= 12)


def parse_local(date_text: str, time_text: str) -> datetime:
    """Local birth time. Times without am/pm are read as 24-hour."""
    clock = parse_clock(time_text)
    return parse_date(date_text).replace(hour=clock.hour, minute=clock.minute)


def resolve_birth(inp: BirthInput) -> ResolvedBirth | NeedsDisambiguation:
    load_profile(inp.profile)
    local = parse_local(inp.date_text, inp.time_text)

    if inp.place_choice:
        place = geo.get_place(inp.place_choice)
        if place is None:
            raise PlaceNotFound(f"unknown place id {inp.place_choice!r}")
    else:
        places = geo.find_places(inp.place_text)
        if not places:
            raise PlaceNotFound(f"no place called {inp.place_text!r}; try the nearest town or add ', CC'")
        if len(places) > 1:
            return NeedsDisambiguation("place", tuple(places))
        place = places[0]

    res = timestd.resolve_local_time(local, place, inp.fold)
    if isinstance(res, timestd.AmbiguousTime):
        return NeedsDisambiguation("time", res.options)
    return ResolvedBirth(
        local=local,
        utc=res.utc,
        place=place,
        provenance=Provenance(
            res.offset,
            res.source,
            res.confidence,
            res.warning,
            place_approximate=bool(inp.approx_for),
            approx_note=(
                f"birthplace {inp.approx_for!r} was not found; this chart uses nearby {place.label}"
                if inp.approx_for
                else None
            ),
        ),
        profile=inp.profile,
    )


@lru_cache(maxsize=1)
def _ephemeris_id() -> str:
    if not EPHEMERIS_PATH.exists():
        return "de440s missing"
    return "de440s " + hashlib.sha256(EPHEMERIS_PATH.read_bytes()).hexdigest()[:12]


@lru_cache(maxsize=1)
def _timestd_version() -> str:
    h = hashlib.sha256()
    for path in sorted(TIME_STANDARDS_DIR.glob("*.yaml")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


@lru_cache(maxsize=16)
def data_info(profile_id: str = DEFAULT_PROFILE) -> VersionStamp:
    profile = load_profile(profile_id)
    return VersionStamp(
        git_sha=os.environ.get("GIT_SHA", "dev"),
        rules_hash=rules_hash(),
        profile_id=profile.id,
        profile_hash=profile.sha256,
        timestd_version=_timestd_version(),
        tzdata_version=importlib.metadata.version("tzdata"),
        ephemeris=_ephemeris_id(),
        gazetteer=geo.gazetteer_stamp(),
    )


@lru_cache(maxsize=16)
def _rules(schools: tuple[str, ...]):
    return tuple(load_rules(schools=schools))


@lru_cache(maxsize=64)
def natal_report(birth: ResolvedBirth) -> NatalReport:
    profile = load_profile(birth.profile)
    chart = ephemeris.compute_chart(
        birth.utc, birth.place.latitude, birth.place.longitude, profile.ayanamsa, profile.node
    )
    dashas = vimshottari(chart.planets["moon"].longitude, birth.utc, profile.dasha_year_days)
    yogas = fired(chart, list(_rules(profile.schools)))
    return NatalReport(
        birth=birth,
        chart=chart,
        dashas=tuple(dashas),
        yogas=tuple(yogas),
        stamp=data_info(profile.id),
        validated=profile.validated,
    )


def today_report(birth: ResolvedBirth, now: datetime) -> TodayReport:
    natal = natal_report(birth)
    profile = load_profile(birth.profile)
    sky = ephemeris.compute_chart(now, birth.place.latitude, birth.place.longitude, profile.ayanamsa, profile.node)
    moon_sign = sign_index(natal.chart.planets["moon"].longitude)
    transits = tuple(
        (g, house_from(moon_sign, sign_index(sky.planets[g].longitude))) for g in TRANSIT_GRAHAS
    )
    dasha = current_dasha(natal.chart.planets["moon"].longitude, birth.utc, now, profile.dasha_year_days)
    return TodayReport(natal=natal, sky=sky, now=now, current_dasha=dasha, transit_houses=transits)


def rahu_kaala_for(place: Place, now: datetime) -> RahuKaala | None:
    """Rahu Kaala for the local calendar day it is `now` at `place`; None if the Sun does not
    rise and set that day."""
    day = now.astimezone(ZoneInfo(place.tz)).date()
    return daylight.rahu_kaala(place.latitude, place.longitude, place.tz, day)


def warm() -> VersionStamp:
    """Load kernel, indexes, rules and profile up front so the first user does not wait."""
    ephemeris._kernel()
    ephemeris._timescale()
    geo.find_places("Pune")
    timestd.load_standards()
    _rules(load_profile().schools)
    return data_info()
