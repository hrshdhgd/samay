import os
import time
from datetime import date

import pytest

from samay.engine import observances
from samay.engine.errors import SampradayaNotSet
from samay.engine.observances import (
    Rule,
    Viddha,
    find_next,
    observances_between,
    observances_for,
)
from samay.engine.panchang import Site
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE = Site(18.5196, 73.8553, "Asia/Kolkata")
NOV_DEC = (date(2026, 11, 1), date(2026, 12, 31))
EKADASHI = Rule(tithis=(11, 26))


def summary(found):
    return [(o.primary, o.kind, [(a.day, a.reason) for a in o.alternates]) for o in found]


def test_sunrise_rule_marks_a_kshaya_ekadashi_and_attaches_the_other_day():
    found = observances_between(EKADASHI, PUNE, *NOV_DEC, margin_minutes=3)
    assert summary(found) == [
        (date(2026, 11, 5), "single", []),
        (date(2026, 11, 20), "kshaya", [(date(2026, 11, 21), "kshaya")]),
        (date(2026, 12, 4), "single", []),
        (date(2026, 12, 20), "single", []),
    ]


def test_kshaya_can_be_resolved_to_the_next_day_instead():
    rule = Rule(tithis=(11, 26), on_kshaya="next_day")
    kshaya = next(o for o in observances_between(rule, PUNE, *NOV_DEC) if o.kind == "kshaya")
    assert kshaya.primary == date(2026, 11, 21) and kshaya.alternates[0].day == date(2026, 11, 20)


def test_kshaya_can_make_no_claim():
    rule = Rule(tithis=(11, 26), on_kshaya="none")
    kshaya = next(o for o in observances_between(rule, PUNE, *NOV_DEC) if o.kind == "kshaya")
    assert kshaya.primary is None


def test_dashami_viddha_rejects_the_day_and_pushes_the_observance_on():
    viddha = Viddha(tithis=(10, 25), anchor="sunrise", start_minutes=-96, end_minutes=0)
    rule = Rule(tithis=(11, 26), on_kshaya="next_day", viddha=viddha)
    found = observances_between(rule, PUNE, *NOV_DEC)
    assert [o.primary for o in found] == [
        date(2026, 11, 5),
        date(2026, 11, 21),
        date(2026, 12, 4),
        date(2026, 12, 20),
    ]
    # 26 May 2026: Shukla Ekadashi holds the 05:58 sunrise, but Dashami is still running 96 minutes before it.
    # Ekadashi also holds the 27 May sunrise, so without viddha this is a vriddhi on 26 May.
    may = (date(2026, 5, 25), date(2026, 5, 28))
    assert [(o.primary, o.kind) for o in observances_between(EKADASHI, PUNE, *may)] == [
        (date(2026, 5, 26), "vriddhi")
    ]
    assert [(o.primary, o.kind) for o in observances_between(rule, PUNE, *may)] == [
        (date(2026, 5, 27), "single")
    ]


def test_a_window_spanning_two_sunrises_is_a_vriddhi_with_a_choice_of_day():
    # A 48-hour window reaches back over every Ekadashi, so each one is a vriddhi. Most lie inside three days'
    # windows; the short Shukla Ekadashi of 20-21 Nov (07:16 to 06:32 IST) only inside those ending at the
    # 21 and 22 Nov sunrises.
    wide = {
        "tithis": (11, 26),
        "anchor": "sunrise",
        "start_minutes": -2880,
        "end_minutes": 0,
    }
    first = [o for o in observances_between(Rule(**wide), PUNE, *NOV_DEC) if o.kind == "vriddhi"]
    last = [
        o for o in observances_between(Rule(**wide, on_vriddhi="last"), PUNE, *NOV_DEC) if o.kind == "vriddhi"
    ]
    assert [(o.primary, o.alternates[0].day) for o in first] == [
        (date(2026, 11, 5), date(2026, 11, 7)),
        (date(2026, 11, 21), date(2026, 11, 22)),
        (date(2026, 12, 4), date(2026, 12, 6)),
        (date(2026, 12, 20), date(2026, 12, 22)),
    ]
    assert [(o.primary, o.alternates[0].day) for o in last] == [
        (date(2026, 11, 7), date(2026, 11, 5)),
        (date(2026, 11, 22), date(2026, 11, 21)),
        (date(2026, 12, 6), date(2026, 12, 4)),
        (date(2026, 12, 22), date(2026, 12, 20)),
    ]


def test_pradosha_window_after_sunset():
    rule = Rule(tithis=(13, 28), anchor="sunset", start_minutes=0, end_minutes=72)
    found = observances_between(rule, PUNE, date(2026, 11, 1), date(2026, 12, 15))
    assert [o.primary for o in found] == [
        date(2026, 11, 6),
        date(2026, 11, 22),
        date(2026, 12, 6),
    ]


def test_a_boundary_inside_the_margin_adds_a_calculation_alternate():
    # With a huge margin every sunrise-instant decision is within reach of the next day's sunrise.
    found = observances_between(EKADASHI, PUNE, date(2026, 12, 3), date(2026, 12, 5), margin_minutes=24 * 60)
    assert any(a.reason == "calculation" for o in found for a in o.alternates)


def test_sampradaya_picks_the_rule_and_the_other_traditions_become_named_alternates():
    rules = {
        "smarta": Rule(tithis=(11, 26), on_kshaya="start_day"),
        "madhva": Rule(tithis=(11, 26), on_kshaya="next_day"),
    }
    found = observances_for(rules, "smarta", PUNE, *NOV_DEC)
    kshaya = next(o for o in found if o.kind == "kshaya")
    assert kshaya.primary == date(2026, 11, 20)
    assert [(a.day, a.reason) for a in kshaya.alternates if a.reason == "madhva convention"] == [
        (date(2026, 11, 21), "madhva convention")
    ]


def test_no_sampradaya_means_no_day_is_named():
    with pytest.raises(SampradayaNotSet):
        observances_for({"smarta": EKADASHI, "madhva": EKADASHI}, None, PUNE, *NOV_DEC)


def test_a_rule_that_does_not_depend_on_tradition_needs_none():
    assert observances_for({"all": EKADASHI}, None, PUNE, *NOV_DEC)


def test_find_next_returns_the_first_upcoming_day():
    nxt = find_next({"all": EKADASHI}, None, PUNE, date(2026, 11, 6))
    assert nxt.primary == date(2026, 11, 20)
    assert find_next(
        {"all": Rule(tithis=(11, 26), on_kshaya="none")}, None, PUNE, date(2026, 11, 6)
    ).primary == date(2026, 12, 4)


@pytest.mark.skipif(os.environ.get("SAMAY_SLOW_CI") == "1", reason="timing guard skipped on slow CI")
def test_observance_search_is_fast_enough_for_a_chat_answer():
    # Cold caches, so this measures the search itself and not lookups left behind by the tests above.
    observances._tithi_at.cache_clear()
    observances._sun.cache_clear()
    started = time.perf_counter()
    observances_between(EKADASHI, PUNE, *NOV_DEC)
    assert time.perf_counter() - started < 5.0
    observances._tithi_at.cache_clear()
    observances._sun.cache_clear()
    started = time.perf_counter()
    find_next({"all": EKADASHI}, None, PUNE, date(2026, 11, 6))
    assert time.perf_counter() - started < 3.0


def _walked(begin, stop):
    """Every tithi from the one holding `begin` up to `stop`, found one after another (the slow, plain way)."""
    from datetime import timedelta

    from samay.engine.panchang import element_at

    tithi, out = element_at("tithi", begin), []
    while tithi.start < stop:
        out.append(tithi)
        tithi = element_at("tithi", tithi.end + timedelta(seconds=1))
    return out


def test_the_sampled_tithis_are_the_walked_ones():
    from datetime import UTC, datetime

    begin, stop = datetime(2026, 11, 20, 18, 30, tzinfo=UTC), datetime(2027, 1, 3, 18, 30, tzinfo=UTC)
    walked = _walked(begin, stop)
    points = observances._tithi_points(begin, stop, "lahiri_mean")
    sampled = [observances._tithi_at(t, "lahiri_mean") for _, t in points]
    assert [n for n, _ in points] == [t.number for t in sampled] == [t.number for t in walked]
    assert all(
        abs((a.start - b.start).total_seconds()) <= 2 and abs((a.end - b.end).total_seconds()) <= 2
        for a, b in zip(sampled, walked, strict=True)
    )


@pytest.mark.skipif(os.environ.get("SAMAY_SLOW_CI") == "1", reason="timing guard skipped on slow CI")
def test_a_year_of_every_observance_is_fast_enough_for_a_chat_answer():
    from samay.engine.panchang_profile import load_panchang_profile

    profile = load_panchang_profile()
    observances._tithi_at.cache_clear()
    observances._sun.cache_clear()
    started = time.perf_counter()
    for spec in profile.observances.values():
        observances_for(
            spec.rules,
            profile.sampradaya,
            PUNE,
            date(2029, 1, 1),
            date(2029, 12, 31),
            profile.ayanamsa,
            profile.margin_minutes,
            profile.sunrise_definition,
        )
    # About 2 s on a laptop; GitHub's shared runners (CI=true) take 5-9 times as long. Still tight enough to catch a
    # slow-down of an order of magnitude, which is what this guard is for.
    limit = 60.0 if os.environ.get("CI") else 6.0
    assert time.perf_counter() - started < limit


def test_a_moonrise_rule_names_the_day_chaturthi_is_current_at_moonrise():
    mangaluru = Site(12.9141, 74.8560, "Asia/Kolkata")
    rule = Rule(tithis=(19,), anchor="moonrise")
    found = observances_between(rule, mangaluru, date(2026, 11, 20), date(2026, 12, 5))
    assert [o.primary for o in found] == [date(2026, 11, 27)]
