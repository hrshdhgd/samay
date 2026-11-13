"""The only API front ends call. Synchronous; the bot runs it in a worker thread."""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from .engine import (
    antardasha,
    ashtakavarga,
    daylight,
    death_timing,
    death_transits,
    entries,
    ephemeris,
    geo,
    gochara,
    house_effects,
    house_timing,
    timestd,
    upagrahas,
)
from .engine.daylight import RahuKaala
from .engine.errors import InvalidInput, PlaceNotFound
from .engine.geo import Place
from .engine.paths import EPHEMERIS_PATH, TIME_STANDARDS_DIR
from .engine.profiles import DEFAULT_PROFILE, load_profile
from .engine.rules import fired, load_rules, rules_hash
from .engine.vedic import antardashas, current_dasha, house_from, sign_index, vimshottari
from .models import (
    BirthInput,
    NatalReport,
    NeedsDisambiguation,
    OutlookReport,
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


# span -> (length, sampling step, planets shown, whether to check vedha). The Moon changes sign every ~2.5 days, so it
# is shown only for a week or a fortnight; over a year or more only the slow planets mark the time.
_FAST = ("moon", "sun", "mercury", "venus", "mars", "jupiter", "saturn", "rahu", "ketu")
OUTLOOK_SPANS = {
    "week": (timedelta(days=7), timedelta(hours=1), _FAST, True),
    "fortnight": (timedelta(days=14), timedelta(hours=1), _FAST, True),
    "month": (timedelta(days=30), timedelta(hours=3), _FAST[1:], True),
    "year": (timedelta(days=365), timedelta(days=1), ("jupiter", "saturn", "rahu", "ketu"), False),
    "years": (timedelta(days=5 * 365 + 1), timedelta(days=1), ("jupiter", "saturn", "rahu", "ketu"), False),
}


def outlook_report(birth: ResolvedBirth, now: datetime, span: str, tz: str | None = None) -> OutlookReport:
    """The planets' transits over the period ahead, from the natal Moon sign, read by Phaladeepika chapter 26."""
    length, step, planets, check_vedha = OUTLOOK_SPANS[span]
    natal = natal_report(birth)
    profile = load_profile(birth.profile)
    start = now.astimezone(UTC)
    end = start + length
    times = [start + step * k for k in range(int(length / step) + 1)]
    track = ephemeris.sidereal_track(times, profile.ayanamsa, profile.node)
    moon_lon = natal.chart.planets["moon"].longitude
    moon_sign = sign_index(moon_lon)
    rules = gochara.load_rules()
    ashtaka = ashtakavarga.load_rules()
    points = ashtakavarga.bhinna(ashtaka, ashtakavarga.positions(natal.chart))
    found = gochara.stays(times, track, moon_sign, planets, rules, check_vedha, points)
    changes = []
    for maha in natal.dashas:
        if maha.end <= start or maha.start >= end:
            continue
        changes += [(maha.lord, a) for a in antardashas(maha) if start < a.start < end]
    at_start = current_dasha(moon_lon, birth.utc, start, profile.dasha_year_days)
    sub = antardasha.load_rules()
    pairs = [(at_start[0].lord, at_start[1].lord)] if at_start else []
    pairs += [(lord, a.lord) for lord, a in changes]
    results = tuple((m, a, *sub.result(m, a)) for m, a in dict.fromkeys(pairs) if sub.result(m, a))
    return OutlookReport(
        natal=natal, span=span, start=start, end=end, tz=tz or birth.place.tz, moon_sign=moon_sign,
        stays=tuple(found), dasha_at_start=at_start,
        dasha_changes=tuple(changes), rules_level=rules.level, rules_edition=rules.edition, rules_pages=rules.pages,
        antardasha=results, antardasha_edition=sub.edition, antardasha_pages=sub.pages, antardasha_checked=sub.servable,
        ashtaka_checked=ashtaka.servable, ashtaka_meaning=tuple(sorted(ashtaka.meaning.items())) if ashtaka.servable else (),
        ashtaka_variants=sum(1 for v in ashtaka.variants if "phaladeepika" in v),
    )


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
    # Sourced answers and chapter XX: a missing data folder must stop start-up, not silently empty the answers.
    for folder in (entries.ENTRIES_DIR, house_effects.RULES_PATH.parent):
        if not folder.is_dir():
            raise FileNotFoundError(f"required data folder is missing: {folder}")
    entries.load_entries()
    house_effects.load_rules()
    return data_info()


TIMING_YEARS = 3


def timing_report(birth: ResolvedBirth, now: datetime, area: str, tz: str | None = None) -> house_timing.Timing | None:
    """Phaladeepika's timing rules for a life area over the next TIMING_YEARS years, one day at a time (noon UTC). None until the rules are
    checked."""
    rules = house_timing.load_rules()
    if not rules.servable or area not in rules.areas:
        return None
    natal = natal_report(birth)
    profile = load_profile(birth.profile)
    first = now.astimezone(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    times = [first + timedelta(days=d) for d in range(TIMING_YEARS * 365 + 1)]
    track = ephemeris.sidereal_track(times, profile.ayanamsa, profile.node)
    found = house_timing.find(rules, natal.chart, natal.dashas, times, track, area)
    return replace(found, tz=tz or birth.place.tz) if found else None


DEATH_TIMING_YEARS = 5


def death_timing_report(birth: ResolvedBirth, now: datetime, tz: str | None = None) -> death_timing.DeathTiming | None:
    """Phaladeepika's death-timing conditions as stretches of days over the next DEATH_TIMING_YEARS years (noon UTC, one per day). None until checked.
    Never a date: the book names conditions only."""
    rules = death_timing.load_rules()
    if not rules.servable:
        return None
    natal = natal_report(birth)
    profile = load_profile(birth.profile)
    first = now.astimezone(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    times = [first + timedelta(days=d) for d in range(DEATH_TIMING_YEARS * 365 + 1)]
    track = ephemeris.sidereal_track(times, profile.ayanamsa, profile.node)
    found = death_timing.find(rules, natal.chart, natal.dashas, times, track)
    if not found:
        return None
    exits = death_transits.load_rules()
    if exits.servable:  # chapter 17 adds its transit rules, using Gulika and Yamakantaka when they can be worked out
        ups = upagraha_report(birth, force=True)
        longs = {p.key: p.longitude for p in ups.points} if ups else {}
        night = None if not ups or not ups.when else ups.when == "night"
        found = replace(found, results=found.results + death_transits.find(exits, natal.chart, times, track, longs, night))
    return replace(found, tz=tz or birth.place.tz)


def upagraha_report(birth: ResolvedBirth, force: bool = False) -> upagrahas.Upagrahas | None:
    """Gulika and the other upagrahas of this birth, by Phaladeepika chapter 25. None until the rules are checked. `force` works the points out anyway,
    for a rule (chapter 17) that needs a point but shows only its own result, never the upagraha texts."""
    rules = upagrahas.load_rules()
    if not rules.servable and not force:
        return None
    if not rules.servable:
        rules = replace(rules, level="translation-checked", checked_by="internal")
    natal = natal_report(birth)
    profile = load_profile(birth.profile)
    p = birth.place

    def ascendant_at(moment: datetime) -> float:
        return ephemeris.compute_chart(moment, p.latitude, p.longitude, profile.ayanamsa, profile.node).ascendant

    local = birth.utc.astimezone(ZoneInfo(p.tz))
    return upagrahas.find(rules, natal.chart, local, p.latitude, p.longitude, p.tz, ascendant_at)
