"""The only API front ends call. Synchronous; the bot runs it in a worker thread."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
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
    observances,
    panchang,
    panchang_profile,
    planet_strength,
    timestd,
    tulu,
    upagrahas,
)
from .engine.daylight import RahuKaala
from .engine.errors import InvalidInput, PlaceNotFound, SampradayaNotSet
from .engine.geo import Place
from .engine.paths import EPHEMERIS_PATH, PROFILES_DIR, TIME_STANDARDS_DIR
from .engine.profiles import DEFAULT_PROFILE, load_profile
from .engine.rules import fired, load_rules, rules_hash
from .engine.vedic import (
    antardashas,
    current_dasha,
    house_from,
    sign_index,
    vimshottari,
)
from .engine.vedic import nakshatra as nakshatra_of
from .models import (
    BirthInput,
    DayReport,
    NatalReport,
    NeedsDisambiguation,
    NextObservanceReport,
    ObservanceDay,
    ObservanceListReport,
    OutlookReport,
    PanchangReport,
    Provenance,
    ResolvedBirth,
    TodayReport,
    VersionStamp,
)

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%b %d %Y",
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
        birth.utc,
        birth.place.latitude,
        birth.place.longitude,
        profile.ayanamsa,
        profile.node,
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
    sky = ephemeris.compute_chart(
        now, birth.place.latitude, birth.place.longitude, profile.ayanamsa, profile.node
    )
    moon_sign = sign_index(natal.chart.planets["moon"].longitude)
    transits = tuple((g, house_from(moon_sign, sign_index(sky.planets[g].longitude))) for g in TRANSIT_GRAHAS)
    dasha = current_dasha(natal.chart.planets["moon"].longitude, birth.utc, now, profile.dasha_year_days)
    return TodayReport(natal=natal, sky=sky, now=now, current_dasha=dasha, transit_houses=transits)


# span -> (length, sampling step, planets shown, whether to check vedha). The Moon changes sign every ~2.5 days, so it
# is shown only for a day, a week or a fortnight; over a year or more only the slow planets mark the time. "day" is the
# engine's span for a one-day reading (day_report); it is not a period a question names, so it has no outlook topic.
_FAST = ("moon", "sun", "mercury", "venus", "mars", "jupiter", "saturn", "rahu", "ketu")
OUTLOOK_SPANS = {
    "day": (timedelta(days=1), timedelta(hours=1), _FAST, True),
    "week": (timedelta(days=7), timedelta(hours=1), _FAST, True),
    "fortnight": (timedelta(days=14), timedelta(hours=1), _FAST, True),
    "month": (timedelta(days=30), timedelta(hours=3), _FAST[1:], True),
    "year": (
        timedelta(days=365),
        timedelta(days=1),
        ("jupiter", "saturn", "rahu", "ketu"),
        False,
    ),
    "years": (
        timedelta(days=5 * 365 + 1),
        timedelta(days=1),
        ("jupiter", "saturn", "rahu", "ketu"),
        False,
    ),
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
        natal=natal,
        span=span,
        start=start,
        end=end,
        tz=tz or birth.place.tz,
        moon_sign=moon_sign,
        stays=tuple(found),
        dasha_at_start=at_start,
        dasha_changes=tuple(changes),
        rules_level=rules.level,
        rules_edition=rules.edition,
        rules_pages=rules.pages,
        antardasha=results,
        antardasha_edition=sub.edition,
        antardasha_pages=sub.pages,
        antardasha_checked=sub.servable,
        ashtaka_checked=ashtaka.servable,
        ashtaka_meaning=(tuple(sorted(ashtaka.meaning.items())) if ashtaka.servable else ()),
        ashtaka_variants=sum(1 for v in ashtaka.variants if "phaladeepika" in v),
    )


DAYS_AHEAD = {"today": 0, "tomorrow": 1}


def day_report(birth: ResolvedBirth, now: datetime, which: str, home: Place | None = None) -> DayReport:
    """One local day for the person: today or tomorrow by the calendar where they live now (`home`), or by UTC when
    that is not known. The transits run from that day's local midnight for a day; the panchang and Rahu Kaala are
    worked out at the home place only."""
    tz = home.tz if home is not None else "UTC"
    zone = ZoneInfo(tz)
    day = now.astimezone(zone).date() + timedelta(days=DAYS_AHEAD[which])
    start = datetime.combine(day, time(), zone)
    outlook = outlook_report(birth, start, "day", tz)
    return DayReport(
        which=which,
        day=day,
        outlook=outlook,
        place_label=home.label if home is not None else None,
        panchang=panchang_report(home, day) if home is not None else None,
        rahu=rahu_kaala_for(home, start) if home is not None else None,
        birth_nakshatra=nakshatra_of(outlook.natal.chart.planets["moon"].longitude)[0],
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
    # Panchang conventions: a missing or malformed profile must stop start-up too.
    _panchang_profile()
    tulu.load_tulu_profile(PANCHANG_PROFILES_DIR)
    return data_info()


TIMING_YEARS = 3


def timing_report(
    birth: ResolvedBirth, now: datetime, area: str, tz: str | None = None
) -> house_timing.Timing | None:
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


def death_timing_report(
    birth: ResolvedBirth, now: datetime, tz: str | None = None
) -> death_timing.DeathTiming | None:
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
    if (
        exits.servable
    ):  # chapter 17 adds its transit rules, using Gulika and Yamakantaka when they can be worked out
        ups = upagraha_report(birth, force=True)
        longs = {p.key: p.longitude for p in ups.points} if ups else {}
        night = None if not ups or not ups.when else ups.when == "night"
        found = replace(
            found,
            results=found.results + death_transits.find(exits, natal.chart, times, track, longs, night),
        )
    return replace(found, tz=tz or birth.place.tz)


def upagraha_report(birth: ResolvedBirth, force: bool = False) -> upagrahas.Upagrahas | None:
    """Gulika and the other upagrahas of this birth, by Phaladeepika chapter 25. None until the rules are checked. `force` works the points out anyway,
    for a rule (chapter 17) that needs a point but shows only its own result, never the upagraha texts.
    """
    rules = upagrahas.load_rules()
    if not rules.servable and not force:
        return None
    if not rules.servable:
        rules = replace(rules, level="translation-checked", checked_by="internal")
    natal = natal_report(birth)
    profile = load_profile(birth.profile)
    p = birth.place

    def ascendant_at(moment: datetime) -> float:
        return ephemeris.compute_chart(
            moment, p.latitude, p.longitude, profile.ayanamsa, profile.node
        ).ascendant

    local = birth.utc.astimezone(ZoneInfo(p.tz))
    return upagrahas.find(rules, natal.chart, local, p.latitude, p.longitude, p.tz, ascendant_at)


def strength_report(birth: ResolvedBirth) -> planet_strength.Strengths | None:
    """Which of Phaladeepika's six strengths each planet has. None until the rules are checked."""
    rules = planet_strength.load_rules()
    if not rules.servable:
        return None
    p = birth.place
    local = birth.utc.astimezone(ZoneInfo(p.tz))
    sun = daylight.sun_times(p.latitude, p.longitude, p.tz, local.date())
    night = None if sun is None else not (sun.sunrise <= local < sun.sunset)
    return planet_strength.find(rules, natal_report(birth).chart, night)


PANCHANG_PROFILES_DIR = PROFILES_DIR  # a test may point this at a copy


def _panchang_profile() -> panchang_profile.PanchangProfile:
    return panchang_profile.load_panchang_profile(directory=PANCHANG_PROFILES_DIR)


def _site(place: Place) -> panchang.Site:
    return panchang.Site(place.latitude, place.longitude, place.tz)


def reference_place() -> Place | None:
    """The family's reference place (SAMAY_REFERENCE_PLACE, for example "Mangaluru, IN"), separate from a chat's saved
    home."""
    text = os.environ.get("SAMAY_REFERENCE_PLACE", "").strip()
    if not text:
        return None
    found = geo.find_places(text, limit=1)
    return found[0] if found else None


def observance_explanation(name: str, directory=None) -> list[str]:
    """Checked entries for an observance, in our own words. Unchecked entries are never returned."""
    return [e.english for e in entries.answers_for(f"observance:{name}", directory=directory)]


def nakshatra_explanation(name: str, directory=None) -> list[str]:
    """Checked entries for a nakshatra, in our own words. Unchecked entries are never returned."""
    return [e.english for e in entries.answers_for(f"nakshatra:{name}", directory=directory)]


def _explanation(name: str) -> str | None:
    found = observance_explanation(name)
    return found[0] if found else None


def _as_day(name: str, label: str, o: observances.Observance, explain: bool = True) -> ObservanceDay:
    """The engine may name one alternate day for several reasons (a kshaya day that is also another tradition's day);
    each day is listed once, its reasons joined in the order the engine gave them."""
    reasons: dict[date, list[str]] = {}
    for a in o.alternates:
        reasons.setdefault(a.day, []).append(a.reason)
    alternates = tuple((day, " and ".join(dict.fromkeys(why))) for day, why in reasons.items())
    return ObservanceDay(
        name,
        label,
        o.primary,
        o.kind,
        alternates,
        _explanation(name) if explain else None,
    )


def panchang_report(place: Place, day: date) -> PanchangReport | None:
    """Everything the bot says about one local day at a place. Observance days are named only from verified rules
    and only once the family's tradition is set; otherwise the report says that a claim was withheld.
    """
    profile, site = _panchang_profile(), _site(place)
    facts = panchang.day_facts(site, day, profile.ayanamsa, profile.sunrise_definition)
    if facts is None:
        return None
    tulu_profile = tulu.load_tulu_profile(PANCHANG_PROFILES_DIR)
    date_in_tulu = tulu.tulu_date(
        day,
        place.latitude,
        place.longitude,
        place.tz,
        tulu_profile.cutoff,
        tulu_profile.ayanamsa,
    )
    today: list[ObservanceDay] = []
    needs_tradition = withheld = False
    for spec in profile.observances.values():
        if not spec.verified:
            withheld = True
            continue
        try:
            found = observances.observances_for(
                spec.rules,
                profile.sampradaya,
                site,
                day,
                day,
                profile.ayanamsa,
                profile.margin_minutes,
                profile.sunrise_definition,
            )
        except SampradayaNotSet:
            needs_tradition = True
            continue
        today += [_as_day(spec.name, spec.label, o) for o in found]
    nakshatra_key = facts.nakshatra.name.lower().replace(" ", "-")
    if notes := nakshatra_explanation(nakshatra_key):  # only once a checked entry exists
        today.append(ObservanceDay(nakshatra_key, facts.nakshatra.name, None, "single", (), notes[0]))
    care = tuple(
        n.text
        for n in profile.care_notes
        if (n.tithi is not None and facts.tithi.number == n.tithi)
        or (n.nakshatra is not None and facts.nakshatra.name.lower() == n.nakshatra)
    )
    return PanchangReport(
        place.label,
        place.tz,
        facts,
        date_in_tulu,
        tulu_profile.cutoff,
        tuple(today),
        needs_tradition,
        withheld,
        care,
    )


def observance_care_notes(name: str) -> tuple[str, ...]:
    """Traditional-care texts for the tithi(s) an observance is kept on (Amavasya: tithi 30)."""
    spec = _panchang_profile().observances.get(name)
    if spec is None:
        return ()
    tithis = {t for rule in spec.rules.values() for t in rule.tithis}
    return tuple(n.text for n in _panchang_profile().care_notes if n.tithi in tithis)


def next_observance_report(place: Place, name: str, today: date) -> NextObservanceReport:
    """The next day an observance falls on, or why no day can be named."""
    profile = _panchang_profile()
    spec = profile.observances[name]
    base = {
        "place_label": place.label,
        "tz": place.tz,
        "name": name,
        "label": spec.label,
    }
    if not spec.verified:
        return NextObservanceReport(**base, found=None, claim_available=False, needs_sampradaya=False)
    try:
        found = observances.find_next(
            spec.rules,
            profile.sampradaya,
            _site(place),
            today,
            profile.ayanamsa,
            profile.margin_minutes,
            profile.sunrise_definition,
        )
    except SampradayaNotSet:
        return NextObservanceReport(**base, found=None, claim_available=False, needs_sampradaya=True)
    return NextObservanceReport(
        **base,
        found=None if found is None else _as_day(name, spec.label, found),
        claim_available=True,
        needs_sampradaya=False,
    )


LIST_MAX_DAYS = 366


def observance_list_report(
    place: Place, first: date, last: date, names: tuple[str, ...] = ()
) -> ObservanceListReport:
    """Every day the verified rules name between two local days (inclusive), for the observances in `names` or all
    of them. One engine search per observance covers the whole range. A day is named only from a verified rule and,
    where traditions differ, only once the family's tradition is set. Over LIST_MAX_DAYS nothing is worked out.
    """
    profile, site = _panchang_profile(), _site(place)
    specs = [s for s in profile.observances.values() if not names or s.name in names]
    base = {
        "place_label": place.label,
        "tz": place.tz,
        "first": first,
        "last": last,
        "labels": tuple(s.label for s in specs),
        "filtered": bool(names),
    }
    if (last - first).days + 1 > LIST_MAX_DAYS:
        return ObservanceListReport(**base, days=(), withheld=(), needs_sampradaya=False, too_long=True)
    days: list[ObservanceDay] = []
    needs_tradition = False
    for spec in specs:
        if not spec.verified:
            continue
        try:
            found = observances.observances_for(
                spec.rules,
                profile.sampradaya,
                site,
                first,
                last,
                profile.ayanamsa,
                profile.margin_minutes,
                profile.sunrise_definition,
            )
        except SampradayaNotSet:
            needs_tradition = True
            continue
        days += [_as_day(spec.name, spec.label, o, explain=False) for o in found]
    order = [s.name for s in specs]
    days.sort(
        key=lambda o: (
            o.primary or min((d for d, _ in o.alternates), default=first),
            order.index(o.name),
        )
    )
    return ObservanceListReport(
        **base,
        days=tuple(days),
        withheld=tuple(s.label for s in specs if not s.verified),
        needs_sampradaya=needs_tradition,
        too_long=False,
    )
