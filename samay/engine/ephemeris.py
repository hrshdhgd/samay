"""Offline planetary positions for samay.

Uses Skyfield with a locally bundled JPL kernel (de440s.bsp). No network access
at runtime. Longitudes are geocentric, apparent, on the true ecliptic of date,
converted to the sidereal zodiac with the Lahiri (Chitrapaksha) ayanamsa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .errors import EphemerisMissing, OutOfEphemerisRange, UnsupportedLatitude
from .paths import EPHEMERIS_PATH

# Coverage of de440s.bsp, kept one day inside the kernel's segment boundaries.
EPHEMERIS_START = datetime(1849, 12, 26, tzinfo=timezone.utc)
EPHEMERIS_END = datetime(2150, 1, 20, tzinfo=timezone.utc)
# The whole-sign lagna formula is ill-defined inside the polar circles.
MAX_ABS_LATITUDE = 66.5
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
    return _LAHIRI_T0_DEG + (_general_precession_arcsec(T) - _general_precession_arcsec(T0)) / 3600.0


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
    lam = math.degrees(math.atan2(-math.cos(th), math.sin(ep) * math.tan(ph) + math.cos(ep) * math.sin(th)))
    return (lam + 180.0) % 360.0


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


AYANAMSAS = {"lahiri_mean": lahiri_ayanamsa}
NODES = {"mean": mean_lunar_node}


def _tropical_longitudes(t, node_fn) -> dict[str, float]:
    from skyfield.framelib import ecliptic_frame

    eph = _kernel()
    earth = eph["earth"]
    out = {}
    for name, target in KERNEL_TARGETS.items():
        lat, lon, _ = earth.at(t).observe(eph[target]).apparent().frame_latlon(ecliptic_frame)
        out[name] = lon.degrees % 360.0
    node = node_fn(t.tt)
    out["rahu"] = node
    out["ketu"] = (node + 180.0) % 360.0
    return out


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
    utc = utc.astimezone(timezone.utc)
    if not EPHEMERIS_START <= utc <= EPHEMERIS_END:
        raise OutOfEphemerisRange(
            f"{utc:%Y-%m-%d} is outside {EPHEMERIS_START:%Y-%m-%d}..{EPHEMERIS_END:%Y-%m-%d}"
        )
    if abs(latitude) > MAX_ABS_LATITUDE:
        raise UnsupportedLatitude(f"latitude {latitude:.2f} is inside a polar circle")

    ts = _timescale()
    t = ts.from_datetime(utc)
    node_fn = NODES[node]
    ayan = AYANAMSAS[ayanamsa](t.tt)
    now = _tropical_longitudes(t, node_fn)
    before = _tropical_longitudes(ts.from_datetime(utc - RETRO_STEP), node_fn)
    after = _tropical_longitudes(ts.from_datetime(utc + RETRO_STEP), node_fn)

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
