"""Tithi, nakshatra, karana and yoga for any instant, found by searching the Sun and Moon's sidereal longitudes.

A tithi is each 12 degrees the Moon gains on the Sun, a karana half of that, a nakshatra 13 deg 20' of the Moon's
longitude, a yoga each 13 deg 20' of the Sun's plus the Moon's. These are geocentric, so they do not depend on the
place; the day a tithi counts for does (see observances.py). Searches go 2 hours at a time, then bisect to a second.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from . import ephemeris
from .vedic import NAKSHATRAS

TITHI_DEG = 12.0
KARANA_DEG = 6.0
NAK_DEG = YOGA_DEG = 360.0 / 27.0
COARSE_STEP = timedelta(hours=2)
SEARCH_LIMIT = timedelta(hours=48)
RESOLUTION = timedelta(seconds=1)

TITHI_NAMES = ("Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami", "Ashtami",
               "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi")
KARANA_MOVABLE = ("Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti")
KARANA_FIXED = ("Kimstughna", "Shakuni", "Chatushpada", "Naga")
YOGA_NAMES = ("Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", "Dhriti", "Shula",
              "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana",
              "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti")


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


def _edge(kind: str, t0: datetime, forward: bool, ayanamsa: str) -> datetime:
    """The instant the element holding t0 begins (forward=False) or ends (forward=True), to a second."""
    angle, width = QUANTITIES[kind]
    sign = 1 if forward else -1
    grid = [t0 + sign * COARSE_STEP * i for i in range(int(SEARCH_LIMIT / COARSE_STEP) + 1)]
    values = [angle(s, m) for s, m in _longitudes(grid, ayanamsa)]
    base = int(values[0] // width)
    for i in range(1, len(grid)):
        if int(values[i] // width) != base:
            inside, outside = grid[i - 1], grid[i]
            break
    else:
        raise RuntimeError(f"no {kind} boundary within {SEARCH_LIMIT} of {t0}")
    while abs(outside - inside) > RESOLUTION:
        mid = inside + (outside - inside) / 2
        if int(angle(*_longitudes([mid], ayanamsa)[0]) // width) == base:
            inside = mid
        else:
            outside = mid
    return outside if forward else inside


def _name(kind: str, cell: int) -> str:
    if kind == "tithi":
        return tithi_name(cell + 1)
    if kind == "nakshatra":
        return NAKSHATRAS[cell]
    if kind == "karana":
        return karana_name(cell)
    return YOGA_NAMES[cell]


def element_at(kind: str, utc: datetime, ayanamsa: str = "lahiri_mean") -> Element:
    angle, width = QUANTITIES[kind]
    cell = int(angle(*_longitudes([utc], ayanamsa)[0]) // width)
    return Element(kind, cell + 1, _name(kind, cell), _edge(kind, utc, False, ayanamsa), _edge(kind, utc, True, ayanamsa))
