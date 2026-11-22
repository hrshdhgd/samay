"""Offline planetary positions for samay.

Uses Skyfield with a locally bundled JPL kernel (de440s.bsp). No network access
at runtime. Longitudes are geocentric, apparent, on the true ecliptic of date,
converted to the sidereal zodiac with the Lahiri (Chitrapaksha) ayanamsa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from .errors import EphemerisMissing, OutOfEphemerisRange, UnsupportedLatitude
from .paths import EPHEMERIS_PATH

# Coverage of de440s.bsp, kept one day inside the kernel's segment boundaries.
EPHEMERIS_START = datetime(1849, 12, 26, tzinfo=UTC)
EPHEMERIS_END = datetime(2150, 1, 20, tzinfo=UTC)
# The whole-sign lagna formula is ill-defined inside the polar circles.
MAX_ABS_LATITUDE = 66.5
UTC_LEAP_SECONDS_FROM = datetime(1972, 1, 1, tzinfo=UTC)
# Retrograde is the sign of motion between t - RETRO_STEP and t + RETRO_STEP.
RETRO_STEP = timedelta(hours=1)

# samay name -> JPL kernel target. DE440s carries only the Mars barycentre, which is
# within metres of the planet.
KERNEL_TARGETS = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars barycenter",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
}
GRAHAS = list(KERNEL_TARGETS) + ["rahu", "ketu"]

J2000_JD = 2451545.0
# Lahiri reference: ayanamsa at JD 2435553.5 (1956-03-21), as used by Swiss Ephemeris.
_LAHIRI_T0_JD = 2435553.5
_LAHIRI_T0_DEG = 23.245524743


def _centuries(jd_tt: float) -> float:
    return (jd_tt - J2000_JD) / 36525.0


def _general_precession_arcsec(T: float) -> float:
    """Accumulated general precession in longitude since J2000 (Lieske 1977)."""
    return 5029.0966 * T + 1.11113 * T * T


def lahiri_ayanamsa(jd_tt: float) -> float:
    """Mean Lahiri ayanamsa in degrees. Matches Swiss Ephemeris to ~1 arcsec over 1900-2100.

    TODO(accuracy): compare against swetest output for a set of dates; consider
    adding nutation in longitude if 'true' Chitrapaksha is wanted.
    """
    T = _centuries(jd_tt)
    T0 = _centuries(_LAHIRI_T0_JD)
    return (
        _LAHIRI_T0_DEG
        + (_general_precession_arcsec(T) - _general_precession_arcsec(T0)) / 3600.0
    )


def mean_lunar_node(jd_tt: float) -> float:
    """Tropical longitude of the mean ascending node (Meeus, Astronomical Algorithms 47.7)."""
    T = _centuries(jd_tt)
    omega = 125.0445479 - 1934.1362891 * T + 0.0020754 * T**2 + T**3 / 467441.0
    return omega % 360.0


def mean_obliquity(jd_tt: float) -> float:
    T = _centuries(jd_tt)
    return 23.4392911 - 0.0130042 * T


def ascendant_tropical(ramc_deg: float, lat_deg: float, eps_deg: float) -> float:
    """Tropical ecliptic longitude of the ascendant (Meeus 14.2, quadrant-corrected)."""
    th, ph, ep = map(math.radians, (ramc_deg, lat_deg, eps_deg))
    lam = math.degrees(
        math.atan2(
            -math.cos(th), math.sin(ep) * math.tan(ph) + math.cos(ep) * math.sin(th)
        )
    )
    return (lam + 180.0) % 360.0


SIDEREAL_DEG_PER_MINUTE = (
    360.98564736629 / 1440.0
)  # how fast the local sidereal time (RAMC) turns


def rising_sign_rest_minutes(chart: Chart) -> float:
    """Minutes, at the birth place, until the sidereal ascendant reaches the end of the sign rising at birth: the rising time of the part of the sign still below the
    horizon (Brihat Jataka XXV.12). The ayanamsa and the obliquity are held fixed over those few hours.
    """
    t = _skyfield_time(chart.utc)
    ramc0 = (t.gast * 15.0 + chart.longitude) % 360.0
    eps = mean_obliquity(t.tt)

    def gained(d: float) -> float:
        asc = (
            ascendant_tropical(ramc0 + d, chart.latitude, eps) - chart.ayanamsa
        ) % 360.0
        return (asc - chart.ascendant) % 360.0

    need = 30.0 - chart.ascendant % 30.0
    lo, hi = 0.0, 0.5
    while gained(hi) < need and hi < 360.0:
        lo, hi = hi, hi + 0.5
    for _ in range(40):
        mid = (lo + hi) / 2.0
        lo, hi = (mid, hi) if gained(mid) < need else (lo, mid)
    return hi / SIDEREAL_DEG_PER_MINUTE


@dataclass(frozen=True)
class Placement:
    longitude: float  # sidereal, degrees [0, 360)
    retrograde: bool = False


@dataclass(frozen=True)
class Chart:
    utc: datetime
    latitude: float
    longitude: float
    ayanamsa: float
    ascendant: float  # sidereal longitude
    planets: dict[str, Placement]


@lru_cache(maxsize=1)
def _kernel():
    from skyfield.api import load_file

    if not EPHEMERIS_PATH.exists():
        raise EphemerisMissing(
            f"Ephemeris not found at {EPHEMERIS_PATH}. Run scripts/fetch-ephemeris.sh "
            "(the Docker build bundles it)."
        )
    return load_file(str(EPHEMERIS_PATH))


@lru_cache(maxsize=1)
def _timescale():
    from skyfield.api import load

    return load.timescale(builtin=True)  # bundled leap-second data, no download


def _skyfield_time(utc: datetime):
    """Civil time -> Skyfield Time.

    UTC with leap seconds only exists from 1972. Earlier civil clocks followed mean solar time
    (GMT ~ UT1), so treating them as UTC would shift sidereal time by ~12 s (~3' of lagna).
    """
    ts = _timescale()
    if utc >= UTC_LEAP_SECONDS_FROM:
        return ts.from_datetime(utc)
    seconds = utc.second + utc.microsecond / 1e6
    return ts.ut1(utc.year, utc.month, utc.day, utc.hour, utc.minute, seconds)


AYANAMSAS = {"lahiri_mean": lahiri_ayanamsa}
NODES = {"mean": mean_lunar_node}


def _tropical_longitudes(t, node_fn) -> dict[str, float]:
    from skyfield.framelib import ecliptic_frame

    eph = _kernel()
    earth = eph["earth"]
    out = {}
    for name, target in KERNEL_TARGETS.items():
        _lat, lon, _ = (
            earth.at(t).observe(eph[target]).apparent().frame_latlon(ecliptic_frame)
        )
        out[name] = lon.degrees % 360.0
    node = node_fn(t.tt)
    out["rahu"] = node
    out["ketu"] = (node + 180.0) % 360.0
    return out


def sidereal_track(
    times: list[datetime], ayanamsa: str = "lahiri_mean", node: str = "mean"
) -> dict[str, list[float]]:
    """Sidereal longitude of every graha at each of many moments (UTC-aware, from 1972), in one vectorised pass.
    Used for transits over weeks to years; a chart for one moment is compute_chart."""
    if not times:
        return {g: [] for g in GRAHAS}
    if any(t.tzinfo is None for t in times):
        raise ValueError("times must be timezone-aware")
    utc = [t.astimezone(UTC) for t in times]
    if not (
        max(UTC_LEAP_SECONDS_FROM, EPHEMERIS_START) <= min(utc)
        and max(utc) <= EPHEMERIS_END
    ):
        raise OutOfEphemerisRange(
            f"{min(utc):%Y-%m-%d}..{max(utc):%Y-%m-%d} is outside the supported range"
        )
    t = _timescale().from_datetimes(utc)
    ayan = AYANAMSAS[ayanamsa](t.tt)
    tropical = _tropical_longitudes(t, NODES[node])
    return {g: [float(x) for x in (tropical[g] - ayan) % 360.0] for g in GRAHAS}


def compute_chart(
    utc: datetime,
    latitude: float,
    longitude: float,
    ayanamsa: str = "lahiri_mean",
    node: str = "mean",
) -> Chart:
    """Sidereal chart for a UTC moment and a place (east longitude positive)."""
    if utc.tzinfo is None:
        raise ValueError("utc must be timezone-aware")
    if ayanamsa not in AYANAMSAS:
        raise ValueError(f"unsupported ayanamsa {ayanamsa!r}")
    if node not in NODES:
        raise ValueError(f"unsupported node {node!r}")
    utc = utc.astimezone(UTC)
    if not EPHEMERIS_START <= utc <= EPHEMERIS_END:
        raise OutOfEphemerisRange(
            f"{utc:%Y-%m-%d} is outside {EPHEMERIS_START:%Y-%m-%d}..{EPHEMERIS_END:%Y-%m-%d}"
        )
    if abs(latitude) > MAX_ABS_LATITUDE:
        raise UnsupportedLatitude(f"latitude {latitude:.2f} is inside a polar circle")

    t = _skyfield_time(utc)
    node_fn = NODES[node]
    ayan = AYANAMSAS[ayanamsa](t.tt)
    now = _tropical_longitudes(t, node_fn)
    before = _tropical_longitudes(_skyfield_time(utc - RETRO_STEP), node_fn)
    after = _tropical_longitudes(_skyfield_time(utc + RETRO_STEP), node_fn)

    planets = {}
    for name, lon in now.items():
        delta = ((after[name] - before[name] + 180.0) % 360.0) - 180.0
        retro = name in ("rahu", "ketu") or (name not in ("sun", "moon") and delta < 0)
        planets[name] = Placement(longitude=(lon - ayan) % 360.0, retrograde=retro)

    ramc = (t.gast * 15.0 + longitude) % 360.0
    asc = ascendant_tropical(ramc, latitude, mean_obliquity(t.tt))
    return Chart(
        utc=utc,
        latitude=latitude,
        longitude=longitude,
        ayanamsa=ayan,
        ascendant=(asc - ayan) % 360.0,
        planets=planets,
    )
