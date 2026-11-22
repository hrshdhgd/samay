import itertools
from datetime import UTC, date, datetime, timedelta

import pytest

from samay.engine import panchang
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
IST = timedelta(hours=5, minutes=30)
PUNE = panchang.Site(18.5196, 73.8553, "Asia/Kolkata")


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


def test_day_facts_use_local_sunrise_and_name_the_prevailing_elements():
    facts = panchang.day_facts(PUNE, date(2026, 11, 21))
    assert facts.sunrise.tzinfo is not None and facts.sunrise.utcoffset() == IST
    assert facts.sunrise.strftime("%H:%M") == "06:44" and facts.sunset.strftime("%H:%M") == "17:56"
    assert facts.tithi.name == "Shukla Dwadashi"
    assert facts.nakshatra.name == "Uttara Bhadrapada"  # Revati only begins at 06:50, six minutes after this sunrise


def test_ekadashi_is_at_no_sunrise_on_20_or_21_nov_in_pune():
    assert panchang.day_facts(PUNE, date(2026, 11, 20)).tithi.number == 10
    assert panchang.day_facts(PUNE, date(2026, 11, 21)).tithi.number == 12


def test_the_sunrise_definition_comes_from_the_caller():
    upper = panchang.day_facts(PUNE, date(2026, 11, 21))
    centre = panchang.day_facts(PUNE, date(2026, 11, 21), definition="disc_centre")
    assert centre.sunrise > upper.sunrise


def test_dst_changes_the_local_offset_of_the_sunrise_across_the_clock_change():
    chicago = panchang.Site(44.953, -93.023, "America/Chicago")  # US clocks went back on 1 Nov 2026
    assert panchang.day_facts(chicago, date(2026, 10, 31)).sunrise.utcoffset() == timedelta(hours=-5)
    assert panchang.day_facts(chicago, date(2026, 11, 2)).sunrise.utcoffset() == timedelta(hours=-6)


def test_southern_hemisphere_place_works():
    sydney = panchang.Site(-33.8688, 151.2093, "Australia/Sydney")
    facts = panchang.day_facts(sydney, date(2026, 11, 21))
    assert facts.sunrise.utcoffset() == timedelta(hours=11) and 5 <= facts.sunrise.hour <= 6


def test_polar_day_without_a_sunrise_gives_none():
    assert panchang.day_facts(panchang.Site(69.65, 18.96, "Europe/Oslo"), date(2026, 12, 21)) is None


@pytest.mark.parametrize("kind, last", [("tithi", 29), ("karana", 59)])
def test_a_full_circle_angle_is_the_first_cell_and_just_below_it_the_last(kind, last):
    import math

    width = panchang.QUANTITIES[kind][1]
    assert panchang._cell(360.0, width) == 0
    assert panchang._cell(math.nextafter(360.0, 0.0), width) == last


@pytest.mark.parametrize("kind", ["tithi", "karana", "nakshatra", "yoga"])
def test_a_full_circle_angle_always_names_a_real_element(kind):
    width = panchang.QUANTITIES[kind][1]
    assert panchang._name(kind, panchang._cell(360.0, width))  # no IndexError for any kind
