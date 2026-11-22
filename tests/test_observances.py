from datetime import date

import pytest

from samay.engine.errors import SampradayaNotSet
from samay.engine.observances import Rule, Viddha, find_next, observances_between, observances_for
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
    assert [o.primary for o in found] == [date(2026, 11, 5), date(2026, 11, 21), date(2026, 12, 4), date(2026, 12, 20)]
    # 26 May 2026: Shukla Ekadashi holds the 05:58 sunrise, but Dashami is still running 96 minutes before it.
    # Ekadashi also holds the 27 May sunrise, so without viddha this is a vriddhi on 26 May.
    may = (date(2026, 5, 25), date(2026, 5, 28))
    assert [(o.primary, o.kind) for o in observances_between(EKADASHI, PUNE, *may)] == [(date(2026, 5, 26), "vriddhi")]
    assert [(o.primary, o.kind) for o in observances_between(rule, PUNE, *may)] == [(date(2026, 5, 27), "single")]


def test_a_window_spanning_two_sunrises_is_a_vriddhi_with_a_choice_of_day():
    # A 48-hour window reaches back over every Ekadashi, so each one is a vriddhi. Most lie inside three days'
    # windows; the short Shukla Ekadashi of 20-21 Nov (07:16 to 06:32 IST) only inside those ending at the
    # 21 and 22 Nov sunrises.
    wide = {"tithis": (11, 26), "anchor": "sunrise", "start_minutes": -2880, "end_minutes": 0}
    first = [o for o in observances_between(Rule(**wide), PUNE, *NOV_DEC) if o.kind == "vriddhi"]
    last = [o for o in observances_between(Rule(**wide, on_vriddhi="last"), PUNE, *NOV_DEC) if o.kind == "vriddhi"]
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
    assert [o.primary for o in found] == [date(2026, 11, 6), date(2026, 11, 22), date(2026, 12, 6)]


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
    assert [(a.day, a.reason) for a in kshaya.alternates if a.reason == "madhva convention"] == [(date(2026, 11, 21), "madhva convention")]


def test_no_sampradaya_means_no_day_is_named():
    with pytest.raises(SampradayaNotSet):
        observances_for({"smarta": EKADASHI, "madhva": EKADASHI}, None, PUNE, *NOV_DEC)


def test_a_rule_that_does_not_depend_on_tradition_needs_none():
    assert observances_for({"all": EKADASHI}, None, PUNE, *NOV_DEC)


def test_find_next_returns_the_first_upcoming_day():
    nxt = find_next({"all": EKADASHI}, None, PUNE, date(2026, 11, 6))
    assert nxt.primary == date(2026, 11, 20)
    assert find_next({"all": Rule(tithis=(11, 26), on_kshaya="none")}, None, PUNE, date(2026, 11, 6)).primary == date(2026, 12, 4)
