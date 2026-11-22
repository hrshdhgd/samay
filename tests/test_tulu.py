from datetime import date
from pathlib import Path

import pytest
import yaml

from samay.engine import tulu
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
MANGALURU = (12.9141, 74.8560, "Asia/Kolkata")


def at(day, cutoff="sunset"):
    return tulu.tulu_date(day, *MANGALURU, cutoff)


def test_bisu_2026_is_paggu_1_on_14_april():
    t = at(date(2026, 4, 14))
    assert (t.month, t.day) == ("Paggu", 1)
    assert t.ingress.strftime("%d %b") == "14 Apr"


def test_the_day_before_is_the_last_day_of_the_previous_month():
    t = at(date(2026, 4, 13))
    assert t.month == "Suggi" and t.day >= 29


def test_next_day_cutoff_moves_every_month_start_by_one_civil_day():
    assert (at(date(2026, 4, 14), "next_day").month, at(date(2026, 4, 14), "next_day").day) == ("Suggi", 30)
    assert at(date(2026, 4, 15), "next_day").month == "Paggu" and at(date(2026, 4, 15), "next_day").day == 1


def test_an_ingress_after_sunset_starts_the_month_the_next_civil_day():
    # The Sun entered Vrischika on 16 Nov 2026 at about 19:40 local, after sunset.
    assert (at(date(2026, 11, 16)).month, at(date(2026, 11, 17)).month) == ("Bonthel", "Jarde")
    assert at(date(2026, 11, 17)).day == 1 and at(date(2026, 11, 21)).day == 5


def test_pattanaje_is_besha_10():
    assert (at(date(2026, 5, 24)).month, at(date(2026, 5, 24)).day) == ("Besha", 10)


def test_the_reference_app_spells_the_tenth_and_eleventh_months_puyintel_and_maayi():
    assert (at(date(2026, 1, 14)).month, at(date(2026, 1, 14)).day) == ("Puyintel", 1)
    assert (at(date(2026, 1, 1)).month, at(date(2026, 1, 1)).day) == ("Perarde", 17)


def test_twelve_month_names_in_order():
    assert tulu.MONTHS[0] == "Paggu" and tulu.MONTHS[11] == "Suggi" and len(tulu.MONTHS) == 12
    assert tulu.MONTHS[9] == "Puyintel" and tulu.MONTHS[10] == "Maayi"


def test_unknown_cutoff_is_rejected():
    with pytest.raises(ValueError, match="cutoff"):
        tulu.tulu_date(date(2026, 4, 14), *MANGALURU, "teatime")


ANCHORS = Path(__file__).parent / "fixtures" / "tulu_anchors.yaml"


@pytest.mark.skipif(not ANCHORS.exists(), reason="family anchors not collected yet (plan Task 0)")
def test_every_family_anchor_matches_under_the_profile_cutoff():
    data = yaml.safe_load(ANCHORS.read_text())
    place = data["place"]
    cutoff = tulu.load_tulu_profile().cutoff
    for a in data["anchors"]:
        t = tulu.tulu_date(a["date"], place["latitude"], place["longitude"], place["tz"], cutoff)
        assert (t.month, t.day) == (a["month"], a["day"]), a


CHICAGO = (41.8781, -87.6298, "America/Chicago")


def test_a_25_hour_fall_back_day_ends_at_the_next_local_midnight(monkeypatch):
    from datetime import UTC, datetime

    seen = []
    real = tulu.last_ingress
    monkeypatch.setattr(tulu, "last_ingress", lambda moment, *a: seen.append(moment) or real(moment, *a))
    tulu.tulu_date(date(2026, 11, 1), *CHICAGO, "sunset")
    assert seen[0] == datetime(2026, 11, 2, 5, 59, 59, tzinfo=UTC)  # 23:59:59 CST, not 22:59:59


def test_the_day_count_advances_by_one_across_the_chicago_clock_change():
    days = [tulu.tulu_date(d, *CHICAGO, "sunset") for d in (date(2026, 10, 31), date(2026, 11, 1), date(2026, 11, 2))]
    assert len({t.month for t in days}) == 1
    assert [t.day - days[0].day for t in days] == [0, 1, 2]
