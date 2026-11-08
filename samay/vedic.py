"""Jyotish primitives: signs, nakshatras, houses, navamsa, Vimshottari dasha."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
RASHIS = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
]
SIGN_LORDS = [
    "mars", "venus", "mercury", "moon", "sun", "mercury",
    "venus", "mars", "jupiter", "saturn", "saturn", "jupiter",
]
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta",
    "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
    "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]
NAK_SPAN = 360.0 / 27.0  # 13°20'

# Vimshottari: lord, years (total 120). Nakshatra n is ruled by DASHA_ORDER[n % 9].
DASHA_ORDER = [
    ("ketu", 7), ("venus", 20), ("sun", 6), ("moon", 10), ("mars", 7),
    ("rahu", 18), ("jupiter", 16), ("saturn", 19), ("mercury", 17),
]
DASHA_YEARS = dict(DASHA_ORDER)
YEAR_DAYS = 365.25  # TODO: schools differ (365.25 vs 360 vs sidereal year); make configurable


def sign_index(lon: float) -> int:
    return int((lon % 360.0) // 30.0)


def degree_in_sign(lon: float) -> float:
    return lon % 30.0


def nakshatra(lon: float) -> tuple[int, int]:
    """(nakshatra index 0-26, pada 1-4)."""
    lon %= 360.0
    quarter = int(lon * 108.0 / 360.0 + 1e-9)  # 108 padas; avoids float edge errors
    return (quarter // 4) % 27, quarter % 4 + 1


def house_from(reference_sign: int, sign: int) -> int:
    """Whole-sign house (1-12) of `sign` counted from `reference_sign`."""
    return (sign - reference_sign) % 12 + 1


def navamsa_sign(lon: float) -> int:
    """D9 sign index. Each 3°20' segment of the zodiac maps to the next sign from Aries."""
    return int((lon % 360.0) * 9.0 / 30.0 + 1e-9) % 12


@dataclass(frozen=True)
class Period:
    lord: str
    start: datetime
    end: datetime

    def contains(self, when: datetime) -> bool:
        return self.start <= when < self.end


def _years(y: float) -> timedelta:
    return timedelta(days=y * YEAR_DAYS)


def vimshottari(moon_lon: float, birth: datetime) -> list[Period]:
    """The nine mahadashas, the first one starting (partially elapsed) before birth."""
    idx, _ = nakshatra(moon_lon)
    first = idx % 9
    elapsed = (moon_lon % NAK_SPAN) / NAK_SPAN
    start = birth - _years(elapsed * DASHA_ORDER[first][1])
    periods = []
    for k in range(9):
        lord, yrs = DASHA_ORDER[(first + k) % 9]
        end = start + _years(yrs)
        periods.append(Period(lord, start, end))
        start = end
    return periods


def antardashas(maha: Period) -> list[Period]:
    """Sub-periods of a mahadasha, starting with its own lord."""
    total = maha.end - maha.start
    first = [l for l, _ in DASHA_ORDER].index(maha.lord)
    periods, start = [], maha.start
    for k in range(9):
        lord, yrs = DASHA_ORDER[(first + k) % 9]
        end = start + total * (yrs / 120.0)
        periods.append(Period(lord, start, end))
        start = end
    return periods


def current_dasha(moon_lon: float, birth: datetime, when: datetime) -> tuple[Period, Period] | None:
    for maha in vimshottari(moon_lon, birth):
        if maha.contains(when):
            for antar in antardashas(maha):
                if antar.contains(when):
                    return maha, antar
    return None
