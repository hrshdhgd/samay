from datetime import datetime, timezone

import pytest

from samay.engine import ephemeris
from samay.engine.errors import EphemerisMissing, OutOfEphemerisRange, UnsupportedLatitude
from samay.engine.paths import EPHEMERIS_PATH

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE = (18.52, 73.86)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        ephemeris.compute_chart(datetime(2000, 1, 1), *PUNE)


def test_out_of_range_rejected():
    with pytest.raises(OutOfEphemerisRange):
        ephemeris.compute_chart(datetime(1800, 1, 1, tzinfo=timezone.utc), *PUNE)


def test_polar_latitude_rejected():
    with pytest.raises(UnsupportedLatitude):
        ephemeris.compute_chart(datetime(2000, 1, 1, tzinfo=timezone.utc), 70.0, 20.0)


def test_unknown_ayanamsa_rejected():
    with pytest.raises(ValueError):
        ephemeris.compute_chart(datetime(2000, 1, 1, tzinfo=timezone.utc), *PUNE, ayanamsa="nope")


def test_missing_kernel(monkeypatch, tmp_path):
    ephemeris._kernel.cache_clear()
    monkeypatch.setattr(ephemeris, "EPHEMERIS_PATH", tmp_path / "missing.bsp")
    try:
        with pytest.raises(EphemerisMissing):
            ephemeris.compute_chart(datetime(2000, 1, 1, tzinfo=timezone.utc), *PUNE)
    finally:
        ephemeris._kernel.cache_clear()


@needs_kernel
def test_all_grahas_present():
    c = ephemeris.compute_chart(datetime(2000, 1, 1, 12, tzinfo=timezone.utc), *PUNE)
    assert set(c.planets) == set(ephemeris.GRAHAS)


@needs_kernel
def test_mercury_retrograde_and_direct():
    # Mercury was retrograde 21 Apr - 14 May 2023 and direct in early March 2023.
    retro = ephemeris.compute_chart(datetime(2023, 4, 25, tzinfo=timezone.utc), *PUNE)
    direct = ephemeris.compute_chart(datetime(2023, 3, 1, tzinfo=timezone.utc), *PUNE)
    assert retro.planets["mercury"].retrograde
    assert not direct.planets["mercury"].retrograde
    assert not direct.planets["sun"].retrograde and not direct.planets["moon"].retrograde
