"""Which local day an observance falls on, from a rule stored as data.

A rule names the tithis it is about, an anchor (local sunrise or sunset) and a window measured from that anchor in
minutes. A zero-length window is an instant: the tithi must be current at the anchor. A longer window needs the
tithi to overlap it. The result is always one primary day plus, where the rule is ambiguous, an alternate:
  kshaya  - the tithi is current at no anchor, so on_kshaya picks start_day, next_day or none (no claim);
  vriddhi - it qualifies on two days, so on_vriddhi picks first or last;
  calculation - the outcome changes if the anchor moves by the profile's margin, so the other day is attached;
  "<tradition> convention" - another tradition's rule gives a different day.
Which tradition is right for a family is data (the profile's sampradaya), never a default in code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import daylight
from .ephemeris import sidereal_track
from .errors import SampradayaNotSet
from .panchang import TITHI_DEG, Element, Site, _elongation, element_at

ANCHORS = ("sunrise", "sunset")
KSHAYA_CHOICES = ("start_day", "next_day", "none")
VRIDDHI_CHOICES = ("first", "last")
SEARCH_DAYS = 70  # long enough for the rarest observance here (Amavasya, about 30 days apart)
# Sampling step for finding which tithis a range holds: well under the shortest tithi (about 19 hours), so every
# tithi has at least one sample inside it.
SAMPLE_STEP = timedelta(hours=6)


@dataclass(frozen=True)
class Viddha:
    """A day is rejected when one of these tithis overlaps the window (for example Dashami before dawn)."""

    tithis: tuple[int, ...]
    anchor: str
    start_minutes: int
    end_minutes: int


@dataclass(frozen=True)
class Rule:
    tithis: tuple[int, ...]  # tithi numbers 1-30 (Shukla Ekadashi is 11, Krishna Ekadashi 26)
    anchor: str = "sunrise"
    start_minutes: int = 0
    end_minutes: int = 0
    on_kshaya: str = "start_day"
    on_vriddhi: str = "first"
    viddha: Viddha | None = None


@dataclass(frozen=True)
class Alternate:
    day: date
    reason: str  # kshaya | vriddhi | calculation | "<tradition> convention"


@dataclass(frozen=True)
class Observance:
    primary: date | None  # None when the rule chose to make no claim
    kind: str  # single | kshaya | vriddhi
    alternates: tuple[Alternate, ...]
    tithi_start: datetime  # UTC
    tithi_end: datetime


@lru_cache(maxsize=4096)
def _sun(latitude: float, longitude: float, tz: str, day: date, definition: str):
    return daylight.sun_times(latitude, longitude, tz, day, definition)


def _anchor(site: Site, day: date, anchor: str, definition: str) -> datetime | None:
    sun = _sun(site.latitude, site.longitude, site.tz, day, definition)
    if sun is None:
        return None
    return sun.sunrise if anchor == "sunrise" else sun.sunset


@lru_cache(maxsize=4096)
def _tithi_at(utc: datetime, ayanamsa: str) -> Element:
    """The tithi at an instant, memoised: walks over the same months repeat the same lookups."""
    return element_at("tithi", utc, ayanamsa)


@lru_cache(maxsize=64)
def _tithi_points(begin: datetime, stop: datetime, ayanamsa: str) -> tuple[tuple[int, datetime], ...]:
    """(tithi number, an instant inside it) for each tithi from the one holding `begin` to the one holding `stop`,
    from a single sampled pass. Each instant is the middle sample of its tithi's run, hours from either boundary, so the
    exact element found there is that tithi. Walking tithi by tithi needs one full search for every tithi, wanted or
    not; this needs one search only for those a rule asks about."""
    times, at = [], begin
    while at < stop:
        times.append(at)
        at += SAMPLE_STEP
    times.append(stop)
    track = sidereal_track(times, ayanamsa)
    cells = [
        int(_elongation(s, m) // TITHI_DEG) % 30 for s, m in zip(track["sun"], track["moon"], strict=True)
    ]
    runs: list[list[int]] = []
    for i, cell in enumerate(cells):
        if runs and cells[runs[-1][0]] == cell:
            runs[-1].append(i)
        else:
            runs.append([i])
    return tuple((cells[run[0]] + 1, times[run[len(run) // 2]]) for run in runs)


def _tithis_in(start: datetime, end: datetime, ayanamsa: str) -> set[int]:
    current = _tithi_at(start, ayanamsa)
    found = {current.number}
    while current.end < end:
        current = _tithi_at(current.end + timedelta(seconds=1), ayanamsa)
        found.add(current.number)
    return found


def _qualifies(
    rule: Rule,
    start: datetime,
    end: datetime,
    site: Site,
    day: date,
    ayanamsa: str,
    definition: str,
    delta: int,
) -> bool:
    anchor = _anchor(site, day, rule.anchor, definition)
    if anchor is None:
        return False
    anchor += timedelta(minutes=delta)
    w0, w1 = anchor + timedelta(minutes=rule.start_minutes), anchor + timedelta(minutes=rule.end_minutes)
    hit = start <= w0 < end if rule.start_minutes == rule.end_minutes else max(start, w0) < min(end, w1)
    if hit and rule.viddha is not None:
        v = rule.viddha
        v_anchor = _anchor(site, day, v.anchor, definition)
        if v_anchor is not None:
            v_anchor += timedelta(minutes=delta)
            v0, v1 = (
                v_anchor + timedelta(minutes=v.start_minutes),
                v_anchor + timedelta(minutes=v.end_minutes),
            )
            if _tithis_in(v0, max(v0, v1), ayanamsa) & set(v.tithis):
                return False
    return hit


def _qualified_days(
    rule: Rule,
    start: datetime,
    end: datetime,
    site: Site,
    ayanamsa: str,
    definition: str,
    delta: int,
) -> list[date]:
    zone = ZoneInfo(site.tz)
    # Look far enough either side that every day whose (shifted) window can reach the tithi is tried.
    reach = max(abs(rule.start_minutes), abs(rule.end_minutes)) + abs(delta)
    pad = timedelta(days=1 + -(-reach // (24 * 60)))
    day = (start.astimezone(zone) - pad).date()
    last = (end.astimezone(zone) + pad).date()
    days = []
    while day <= last:
        if _qualifies(rule, start, end, site, day, ayanamsa, definition, delta):
            days.append(day)
        day += timedelta(days=1)
    return days


def _reduce(
    rule: Rule, qualified: list[date], start: datetime, zone: ZoneInfo
) -> tuple[str, date | None, list[date]]:
    if len(qualified) == 1:
        return "single", qualified[0], []
    if not qualified:
        start_day = start.astimezone(zone).date()
        if rule.on_kshaya == "none":
            return "kshaya", None, []
        following = start_day + timedelta(days=1)
        if rule.on_kshaya == "start_day":
            return "kshaya", start_day, [following]
        return "kshaya", following, [start_day]
    first, last = qualified[0], qualified[-1]
    return ("vriddhi", first, [last]) if rule.on_vriddhi == "first" else ("vriddhi", last, [first])


def observances_between(
    rule: Rule,
    site: Site,
    first: date,
    last: date,
    ayanamsa: str = "lahiri_mean",
    margin_minutes: int = 0,
    definition: str = "upper_limb",
) -> list[Observance]:
    """Every occurrence of the rule's tithis that touches [first, last], each resolved to a primary day."""
    zone = ZoneInfo(site.tz)
    begin = datetime(first.year, first.month, first.day, tzinfo=zone).astimezone(UTC) - timedelta(days=1)
    stop = datetime(last.year, last.month, last.day, tzinfo=zone).astimezone(UTC) + timedelta(days=2)
    found = []
    for number, point in _tithi_points(begin, stop, ayanamsa):
        if number not in rule.tithis or (tithi := _tithi_at(point, ayanamsa)).start >= stop:
            continue
        kind, primary, others = _reduce(
            rule,
            _qualified_days(rule, tithi.start, tithi.end, site, ayanamsa, definition, 0),
            tithi.start,
            zone,
        )
        alternates = [Alternate(d, kind) for d in others]
        for delta in (-margin_minutes, margin_minutes) if margin_minutes else ():
            _, shifted, _ = _reduce(
                rule,
                _qualified_days(rule, tithi.start, tithi.end, site, ayanamsa, definition, delta),
                tithi.start,
                zone,
            )
            if shifted is not None and shifted != primary and all(a.day != shifted for a in alternates):
                alternates.append(Alternate(shifted, "calculation"))
        # A rule that makes no claim is still reported (never silently skipped): place it by the tithi itself.
        days = ([primary] if primary is not None else []) + [a.day for a in alternates] or [
            tithi.start.astimezone(zone).date(),
            tithi.end.astimezone(zone).date(),
        ]
        if any(first <= d <= last for d in days):
            found.append(Observance(primary, kind, tuple(alternates), tithi.start, tithi.end))
    return found


def observances_for(
    rules: dict[str, Rule],
    sampradaya: str | None,
    site: Site,
    first: date,
    last: date,
    ayanamsa: str = "lahiri_mean",
    margin_minutes: int = 0,
    definition: str = "upper_limb",
) -> list[Observance]:
    """Apply the family's tradition. `rules` maps a tradition name to its rule, or holds just "all" when the observance
    does not differ between traditions. Other traditions' days appear as named alternates.
    """
    if "all" in rules:
        chosen = "all"
    elif sampradaya is None:
        raise SampradayaNotSet("the family's tradition has not been set")
    elif sampradaya not in rules:
        raise ValueError(f"no rule for tradition {sampradaya!r}")
    else:
        chosen = sampradaya
    primary = observances_between(rules[chosen], site, first, last, ayanamsa, margin_minutes, definition)
    others = {
        name: {
            o.tithi_start: o
            for o in observances_between(rule, site, first, last, ayanamsa, margin_minutes, definition)
        }
        for name, rule in rules.items()
        if name != chosen
    }
    merged = []
    for o in primary:
        extra = []
        for name, table in others.items():
            twin = table.get(o.tithi_start)
            # Named even when the day is already an alternate for another reason: the tradition is the news.
            if twin is not None and twin.primary is not None and twin.primary != o.primary:
                extra.append(Alternate(twin.primary, f"{name} convention"))
        merged.append(
            Observance(
                o.primary,
                o.kind,
                o.alternates + tuple(extra),
                o.tithi_start,
                o.tithi_end,
            )
        )
    return merged


def find_next(
    rules: dict[str, Rule],
    sampradaya: str | None,
    site: Site,
    after: date,
    ayanamsa: str = "lahiri_mean",
    margin_minutes: int = 0,
    definition: str = "upper_limb",
) -> Observance | None:
    """The first observance whose primary day is on or after `after`."""
    found = observances_for(
        rules,
        sampradaya,
        site,
        after,
        after + timedelta(days=SEARCH_DAYS),
        ayanamsa,
        margin_minutes,
        definition,
    )
    upcoming = [o for o in found if o.primary is not None and o.primary >= after]
    return min(upcoming, key=lambda o: o.primary, default=None)
