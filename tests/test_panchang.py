import itertools
from datetime import UTC, datetime, timedelta

import pytest

from samay.engine import panchang
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
IST = timedelta(hours=5, minutes=30)


def ist(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC) - IST


def test_shukla_ekadashi_at_pune_sunrise_boundaries_on_20_21_nov_2026():
    e = panchang.element_at("tithi", ist(20, 12, 0))  # midday on 20 Nov IST
    assert (e.number, e.name) == (11, "Shukla Ekadashi")
    assert abs(e.start - ist(20, 7, 16)) < timedelta(minutes=2)
    assert abs(e.end - ist(21, 6, 32)) < timedelta(minutes=2)


def test_nakshatra_and_its_boundaries():
    e = panchang.element_at("nakshatra", datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    assert (e.number, e.name) == (27, "Revati")
    assert abs(e.start - datetime(2026, 11, 21, 1, 20, 39, tzinfo=UTC)) < timedelta(minutes=2)
    assert abs(e.end - datetime(2026, 11, 22, 0, 24, 55, tzinfo=UTC)) < timedelta(minutes=2)


def test_elements_tile_time_without_gaps_or_overlaps():
    t = datetime(2026, 11, 1, tzinfo=UTC)
    seen = []
    for _ in range(8):
        e = panchang.element_at("tithi", t)
        seen.append(e)
        t = e.end + timedelta(seconds=1)
    for a, b in itertools.pairwise(seen):
        assert b.start - a.end < timedelta(seconds=3)
        assert b.number == a.number % 30 + 1


def test_karana_and_yoga_have_expected_ranges_and_names():
    k = panchang.element_at("karana", datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    y = panchang.element_at("yoga", datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    assert 1 <= k.number <= 60 and k.name in panchang.KARANA_MOVABLE + panchang.KARANA_FIXED
    assert 1 <= y.number <= 27 and y.name == panchang.YOGA_NAMES[y.number - 1]


@pytest.mark.parametrize("number, name", [(1, "Shukla Pratipada"), (11, "Shukla Ekadashi"), (15, "Purnima"),
                                            (16, "Krishna Pratipada"), (26, "Krishna Ekadashi"), (30, "Amavasya")])
def test_tithi_names(number, name):
    assert panchang.tithi_name(number) == name


def test_karana_sequence_has_the_fixed_ones_at_the_ends():
    assert panchang.karana_name(0) == "Kimstughna"
    assert [panchang.karana_name(i) for i in (1, 2, 8)] == ["Bava", "Balava", "Bava"]
    assert [panchang.karana_name(i) for i in (57, 58, 59)] == ["Shakuni", "Chatushpada", "Naga"]


def test_outside_the_ephemeris_range_is_a_plain_error():
    from samay.engine.errors import OutOfEphemerisRange

    with pytest.raises(OutOfEphemerisRange):
        panchang.element_at("tithi", datetime(2200, 1, 1, tzinfo=UTC))
