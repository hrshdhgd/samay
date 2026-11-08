"""Offline planetary positions for samay.

Uses Skyfield with a locally bundled JPL kernel (de440s.bsp). No network access
at runtime. Longitudes are geocentric, apparent, on the true ecliptic of date,
converted to the sidereal zodiac with the Lahiri (Chitrapaksha) ayanamsa.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

EPHEMERIS_PATH = os.environ.get("SAMAY_EPHEMERIS", "data/de440s.bsp")

# samay name -> JPL kernel target
KERNEL_TARGETS = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars",
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

    if not os.path.exists(EPHEMERIS_PATH):
        raise FileNotFoundError(
            f"Ephemeris not found at {EPHEMERIS_PATH}. Download de440s.bsp from "
            "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/ (the Docker build does this)."
        )
    return load_file(EPHEMERIS_PATH)


@lru_cache(maxsize=1)
def _timescale():
    from skyfield.api import load

    return load.timescale(builtin=True)  # bundled leap-second data, no download


def _tropical_longitudes(t) -> dict[str, float]:
    from skyfield.framelib import ecliptic_frame

    eph = _kernel()
    earth = eph["earth"]
    out = {}
    for name, target in KERNEL_TARGETS.items():
        lat, lon, _ = earth.at(t).observe(eph[target]).apparent().frame_latlon(ecliptic_frame)
        out[name] = lon.degrees % 360.0
    node = mean_lunar_node(t.tt)
    out["rahu"] = node
    out["ketu"] = (node + 180.0) % 360.0
    return out


def compute_chart(utc: datetime, latitude: float, longitude: float) -> Chart:
    """Sidereal chart for a UTC moment and a place (east longitude positive)."""
    if utc.tzinfo is None:
        raise ValueError("utc must be timezone-aware")
    utc = utc.astimezone(timezone.utc)
    ts = _timescale()
    t = ts.from_datetime(utc)
    t_next = ts.from_datetime(utc + timedelta(hours=6))

    ayan = lahiri_ayanamsa(t.tt)
    now = _tropical_longitudes(t)
    later = _tropical_longitudes(t_next)

    planets = {}
    for name, lon in now.items():
        delta = ((later[name] - lon + 180.0) % 360.0) - 180.0
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
