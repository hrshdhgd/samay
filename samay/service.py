"""The only API front ends call. Synchronous; the bot runs it in a worker thread."""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
from datetime import datetime
from functools import lru_cache

from .engine import ephemeris, geo, timestd
from .engine.errors import InvalidInput, PlaceNotFound
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

DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
TRANSIT_GRAHAS = ("jupiter", "saturn", "rahu", "ketu")


def parse_local(date_text: str, time_text: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            day = datetime.strptime(date_text.strip(), fmt)
            break
        except ValueError:
            continue
    else:
        raise InvalidInput(f"could not read the date {date_text!r}; use YYYY-MM-DD")
    try:
        t = datetime.strptime(time_text.strip(), "%H:%M")
    except ValueError:
        raise InvalidInput(f"could not read the time {time_text!r}; use HH:MM (24-hour)") from None
    return day.replace(hour=t.hour, minute=t.minute)


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
        provenance=Provenance(res.offset, res.source, res.confidence, res.warning),
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
        gazetteer="geonamescache " + importlib.metadata.version("geonamescache"),
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


def warm() -> VersionStamp:
    """Load kernel, indexes, rules and profile up front so the first user does not wait."""
    ephemeris._kernel()
    ephemeris._timescale()
    geo.find_places("Pune")
    timestd.load_standards()
    _rules(load_profile().schools)
    return data_info()
