"""Tithi, nakshatra, karana and yoga for any instant, found by searching the Sun and Moon's sidereal longitudes.

A tithi is each 12 degrees the Moon gains on the Sun, a karana half of that, a nakshatra 13 deg 20' of the Moon's
longitude, a yoga each 13 deg 20' of the Sun's plus the Moon's. These are geocentric, so they do not depend on the
place; the day a tithi counts for does (see observances.py). Searches go 2 hours at a time, then bisect to a second.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from . import daylight, ephemeris
from .vedic import NAKSHATRAS

TITHI_DEG = 12.0
KARANA_DEG = 6.0
NAK_DEG = YOGA_DEG = 360.0 / 27.0
COARSE_STEP = timedelta(hours=2)
SEARCH_LIMIT = timedelta(hours=48)
RESOLUTION = timedelta(seconds=1)
# How far the true boundary may be from the interpolated guess and still be found in the batched call.
GUESS_SLACK = timedelta(seconds=20)

TITHI_NAMES = (
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
)
KARANA_MOVABLE = ("Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti")
KARANA_FIXED = ("Kimstughna", "Shakuni", "Chatushpada", "Naga")
YOGA_NAMES = (
    "Vishkambha",
    "Priti",
    "Ayushman",
    "Saubhagya",
    "Shobhana",
    "Atiganda",
    "Sukarma",
    "Dhriti",
    "Shula",
    "Ganda",
    "Vriddhi",
    "Dhruva",
    "Vyaghata",
    "Harshana",
    "Vajra",
    "Siddhi",
    "Vyatipata",
    "Variyana",
    "Parigha",
    "Shiva",
    "Siddha",
    "Sadhya",
    "Shubha",
    "Shukla",
    "Brahma",
    "Indra",
    "Vaidhriti",
)


def tithi_name(number: int) -> str:
    """1-15 are Shukla (waxing), 16-30 Krishna (waning); the 15th of each is Purnima or Amavasya."""
    index = (number - 1) % 15
    if index == 14:
        return "Purnima" if number == 15 else "Amavasya"
    return f"{'Shukla' if number <= 15 else 'Krishna'} {TITHI_NAMES[index]}"


def karana_name(cell: int) -> str:
    """cell is 0-59, the half-tithi count from new moon: Kimstughna first, seven movable karanas repeating, then three fixed."""
    if cell == 0:
        return "Kimstughna"
    if cell >= 57:
        return KARANA_FIXED[cell - 56]
    return KARANA_MOVABLE[(cell - 1) % 7]


def _elongation(sun: float, moon: float) -> float:
    return (moon - sun) % 360.0


# kind -> (angle as a function of (sun, moon) sidereal longitudes, width of one element in degrees)
QUANTITIES = {
    "tithi": (_elongation, TITHI_DEG),
    "karana": (_elongation, KARANA_DEG),
    "nakshatra": (lambda sun, moon: moon % 360.0, NAK_DEG),
    "yoga": (lambda sun, moon: (sun + moon) % 360.0, YOGA_DEG),
}


@dataclass(frozen=True)
class Site:
    latitude: float
    longitude: float  # east positive
    tz: str


@dataclass(frozen=True)
class Element:
    kind: str  # tithi | nakshatra | karana | yoga
    number: int  # 1-based; karana is 1-60
    name: str
    start: datetime  # UTC
    end: datetime  # UTC


def _longitudes(times: list[datetime], ayanamsa: str) -> list[tuple[float, float]]:
    track = ephemeris.sidereal_track(times, ayanamsa)
    return list(zip(track["sun"], track["moon"], strict=True))


def _cell(angle: float, width: float) -> int:
    """The element index holding `angle`. An angle of exactly 360.0 (a tiny negative value taken modulo 360) is the
    first cell again, not one past the last."""
    return int(angle // width) % round(360.0 / width)


def _bracket(kind: str, grid: list[datetime], values: list[float], base: int) -> int:
    """Index of the first grid instant past cell `base`; the one before it is still inside."""
    width = QUANTITIES[kind][1]
    for i in range(1, len(grid)):
        if _cell(values[i], width) != base:
            return i
    raise RuntimeError(f"no {kind} boundary within {SEARCH_LIMIT} of {grid[0]}")


def _guess(
    kind: str,
    inside: datetime,
    outside: datetime,
    a_in: float,
    a_out: float,
    base: int,
    forward: bool,
) -> datetime:
    """Where the boundary between two grid instants should be, by linear interpolation of the angle."""
    width = QUANTITIES[kind][1]
    if forward:
        span, part = (a_out - a_in) % 360.0, ((base + 1) * width - a_in) % 360.0
    else:
        span, part = (a_in - a_out) % 360.0, (a_in - base * width) % 360.0
    fraction = min(max(part / span, 0.0), 1.0) if span else 0.5
    return inside + (outside - inside) * fraction


def _plan(
    inside: datetime,
    outside: datetime,
    guess: datetime,
    forward: bool,
    into: list[datetime],
) -> None:
    """Every midpoint the bisection below can visit if the boundary is within GUESS_SLACK of `guess`."""
    while abs(outside - inside) > RESOLUTION:
        mid = inside + (outside - inside) / 2
        into.append(mid)
        if abs(mid - guess) <= GUESS_SLACK:
            _plan(mid, outside, guess, forward, into)
            outside = mid
        elif (mid < guess) == forward:
            inside = mid
        else:
            outside = mid


def _bisect(
    kind: str,
    inside: datetime,
    outside: datetime,
    base: int,
    forward: bool,
    known: dict[datetime, int],
    ayanamsa: str,
) -> datetime:
    """Bisect to a second. Cells already computed in `known` are reused; any other midpoint is computed here,
    so the answer is the plain bisection's whatever the guess was."""
    while abs(outside - inside) > RESOLUTION:
        mid = inside + (outside - inside) / 2
        cell = known.get(mid)
        if cell is None:
            cell = _cells(kind, [mid], ayanamsa)[0]
        if cell == base:
            inside = mid
        else:
            outside = mid
    return outside if forward else inside


def _cells(kind: str, times: list[datetime], ayanamsa: str) -> list[int]:
    angle, width = QUANTITIES[kind]
    return [_cell(angle(s, m), width) for s, m in _longitudes(times, ayanamsa)]


def _name(kind: str, cell: int) -> str:
    if kind == "tithi":
        return tithi_name(cell + 1)
    if kind == "nakshatra":
        return NAKSHATRAS[cell]
    if kind == "karana":
        return karana_name(cell)
    return YOGA_NAMES[cell]


def element_at(kind: str, utc: datetime, ayanamsa: str = "lahiri_mean") -> Element:
    """The element holding `utc`, with its start and end to a second.

    Two ephemeris calls cover the usual case: one for the 2-hour grids either side, one for every midpoint the
    bisections can visit near the interpolated boundaries. Any midpoint the guess missed is computed on its own.
    """
    angle, width = QUANTITIES[kind]
    steps = range(1, int(SEARCH_LIMIT / COARSE_STEP) + 1)
    back = [utc] + [utc - COARSE_STEP * i for i in steps]
    ahead = [utc] + [utc + COARSE_STEP * i for i in steps]
    values = [
        angle(s, m) for s, m in _longitudes([utc, *back[1:], *ahead[1:]], ayanamsa)
    ]
    back_values, ahead_values = values[: len(back)], values[:1] + values[len(back) :]
    cell = _cell(values[0], width)
    edges = []
    for forward, grid, vals in (
        (False, back, back_values),
        (True, ahead, ahead_values),
    ):
        i = _bracket(kind, grid, vals, cell)
        inside, outside = grid[i - 1], grid[i]
        edges.append(
            (
                forward,
                inside,
                outside,
                _guess(kind, inside, outside, vals[i - 1], vals[i], cell, forward),
            )
        )
    candidates: list[datetime] = []
    for forward, inside, outside, guess in edges:
        _plan(inside, outside, guess, forward, candidates)
    known = dict(zip(candidates, _cells(kind, candidates, ayanamsa), strict=True))
    start, end = (
        _bisect(kind, inside, outside, cell, forward, known, ayanamsa)
        for forward, inside, outside, _ in edges
    )
    return Element(kind, cell + 1, _name(kind, cell), start, end)


@dataclass(frozen=True)
class DayFacts:
    day: date  # local calendar day
    sunrise: datetime  # local, timezone-aware
    sunset: datetime
    tithi: Element  # the elements prevailing at local sunrise
    nakshatra: Element
    karana: Element
    yoga: Element


def day_facts(
    site: Site, day: date, ayanamsa: str = "lahiri_mean", definition: str = "upper_limb"
) -> DayFacts | None:
    """What prevails at the place's own sunrise on a local calendar day; None when the Sun does not rise and set."""
    sun = daylight.sun_times(site.latitude, site.longitude, site.tz, day, definition)
    if sun is None:
        return None
    at = sun.sunrise.astimezone(UTC)
    return DayFacts(
        day,
        sun.sunrise,
        sun.sunset,
        *(
            element_at(k, at, ayanamsa)
            for k in ("tithi", "nakshatra", "karana", "yoga")
        ),
    )
