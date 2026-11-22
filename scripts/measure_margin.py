"""Measure the ambiguity margin N (minutes) from the engine's own sensitivity, never from agreement with almanacs.

N = worst sunrise/sunset shift between the two sunrise definitions
  + worst shift of a tithi boundary caused by a 1 arcminute error in the Sun-Moon elongation
  + the shift of a nakshatra boundary caused by the nutation offset (samay's sidereal longitudes include nutation,
    Swiss Ephemeris's do not), rounded up to whole minutes.
Rule differences between traditions are not part of N.

Run: uv run python scripts/measure_margin.py
"""

from datetime import UTC, date, datetime, timedelta
from math import ceil

from samay.engine import daylight, ephemeris

PLACES = [
    (18.5196, 73.8553, "Asia/Kolkata"),
    (12.9141, 74.8560, "Asia/Kolkata"),
    (44.953, -93.023, "America/Chicago"),
    (-33.8688, 151.2093, "Australia/Sydney"),
    (51.5074, -0.1278, "Europe/London"),
    (40.7128, -74.0060, "America/New_York"),
]
DAYS = [date(2026, 1, 1) + timedelta(days=10 * i) for i in range(37)]
ARCMINUTE_DEG = 1 / 60
NUTATION_ARCSEC = 18.0
SAMPLES = (
    365 * 4
)  # every 6 hours for a year; each is paired with a sample one hour later


def sunrise_shift_minutes() -> float:
    worst = 0.0
    for lat, lon, tz in PLACES:
        for day in DAYS:
            a = daylight.sun_times(lat, lon, tz, day)
            b = daylight.sun_times(lat, lon, tz, day, "disc_centre")
            if a and b:
                worst = max(
                    worst,
                    abs((b.sunrise - a.sunrise).total_seconds()),
                    abs((b.sunset - a.sunset).total_seconds()),
                )
    return worst / 60


def _slowest_degrees_per_minute(longitudes) -> float:
    """Slowest rate over the year of a quantity sampled hourly: longitudes(track) -> list of degrees."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = [start + timedelta(hours=6 * i) for i in range(SAMPLES)]
    track = ephemeris.sidereal_track(first + [t + timedelta(hours=1) for t in first])
    values = longitudes(track)
    return min(
        ((values[SAMPLES + i] - values[i]) % 360.0) / 60.0 for i in range(SAMPLES)
    )  # degrees per hour / 60


def _elongation(track) -> list[float]:
    return [(m - s) % 360.0 for s, m in zip(track["sun"], track["moon"], strict=True)]


def boundary_shift_minutes() -> float:
    """Minutes by which a tithi boundary moves for a 1 arcminute elongation error, at the Moon's slowest."""
    return ARCMINUTE_DEG / _slowest_degrees_per_minute(_elongation)


def nutation_shift_minutes() -> float:
    """Minutes by which a nakshatra boundary moves for the nutation offset, at the Moon's slowest."""
    return (NUTATION_ARCSEC / 3600) / _slowest_degrees_per_minute(
        lambda track: track["moon"]
    )


if __name__ == "__main__":
    sun, tithi, nutation = (
        sunrise_shift_minutes(),
        boundary_shift_minutes(),
        nutation_shift_minutes(),
    )
    print(
        f"slowest elongation rate {_slowest_degrees_per_minute(_elongation) * 60:.3f} deg/hour"
    )
    print(
        f"slowest Moon rate {_slowest_degrees_per_minute(lambda t: t['moon']) * 60:.3f} deg/hour"
    )
    print(f"sunrise-definition shift {sun:.2f} min")
    print(f"1' elongation error shifts a tithi boundary by {tithi:.2f} min")
    print(
        f'{NUTATION_ARCSEC:.0f}" nutation offset shifts a nakshatra boundary by {nutation:.2f} min'
    )
    print(f"ambiguity_margin_minutes = {ceil(sun + tithi + nutation)}")
