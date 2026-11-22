import re
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from samay.engine.paths import EPHEMERIS_PATH
from samay.models import NextObservanceReport, ObservanceDay, PanchangReport
from samay.render import panchang as words

IST = timezone(timedelta(hours=5, minutes=30))
needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
DASHA_WORD = re.compile(r"\b(maha|antar)?dasha\b", re.IGNORECASE)  # a word, so "Dashami" (a tithi) is fine


class El:
    def __init__(self, name, end, number=1):
        self.name, self.end, self.number = name, end, number


class Facts:
    sunrise = datetime(2026, 11, 21, 6, 44, tzinfo=IST)
    sunset = datetime(2026, 11, 21, 17, 56, tzinfo=IST)
    tithi = El("Shukla Dwadashi", datetime(2026, 11, 21, 23, 27, tzinfo=UTC), 12)  # 04:57 on 22 Nov in Pune
    nakshatra = El("Uttara Bhadrapada", datetime(2026, 11, 21, 1, 20, tzinfo=UTC))  # 06:50 the same day
    karana = El("Bava", datetime(2026, 11, 21, 12, 20, tzinfo=UTC))
    yoga = El("Siddhi", datetime(2026, 11, 21, 21, 0, tzinfo=UTC))


class Tulu:
    month, day = "Jaarde", 5
    month_starts = date(2026, 11, 17)
    ingress = datetime(2026, 11, 16, 19, 39, tzinfo=IST)


def report(**changes):
    base = {"place_label": "Pune", "tz": "Asia/Kolkata", "facts": Facts, "tulu": Tulu, "cutoff": "sunset",
            "observances": (), "needs_sampradaya": False, "claims_withheld": True}
    base.update(changes)
    return PanchangReport(**base)


def ekadashi(kind="kshaya", alternates=((date(2026, 11, 21), "kshaya and madhva convention"),), explanation=None):
    return ObservanceDay("ekadashi", "Ekadashi", date(2026, 11, 20), kind, alternates, explanation)


def test_day_answer_uses_plain_words_and_local_times():
    text = words.render_day(report(), date(2026, 11, 21))
    assert "Saturday, 21 November 2026" in text and "Pune" in text
    assert "Tithi (the Moon's lunar day): Shukla Dwadashi, until 04:57 on 22 Nov." in text
    assert "Nakshatra (the Moon's star): Uttara Bhadrapada, until 06:50." in text
    assert "06:44" in text and "17:56" in text
    assert "Tulu date: Jaarde 5" in text and "sunset rule" in text
    assert "Rahu" not in text and not DASHA_WORD.search(text)


def test_clock_times_are_the_places_own_time():
    text = words.render_day(report(tz="Europe/London"), date(2026, 11, 21))
    assert "Shukla Dwadashi, until 23:27, then Shukla Trayodashi from 23:27." in text and "Uttara Bhadrapada, until 01:20." in text


def test_unverified_rules_say_plainly_that_no_observance_day_is_named():
    assert "not named" in words.render_day(report(), date(2026, 11, 21)).lower()


def test_missing_tradition_asks_for_it():
    assert "tradition" in words.render_day(report(needs_sampradaya=True), date(2026, 11, 21)).lower()


def test_an_observance_day_shows_its_alternate_and_a_local_panchang_note():
    text = words.render_day(report(observances=(ekadashi(),), claims_withheld=False), date(2026, 11, 20))
    assert "Ekadashi: today." in text and "Saturday, 21 November 2026" in text and "local panchang may differ" in text


def test_on_the_alternate_day_it_is_not_called_the_day_nor_unclear():
    text = words.render_day(report(observances=(ekadashi(),), claims_withheld=False), date(2026, 11, 21))
    assert "Ekadashi: some calendars keep it today" in text and "Friday, 20 November 2026" in text
    assert "Ekadashi: today." not in text and "no clear day" not in text
    assert "Saturday, 21 November 2026" not in text.split("\n", 1)[1]  # today is not listed as a further day
    assert "local panchang may differ" in text


def test_a_rule_that_names_no_day_says_so():
    unclear = ObservanceDay("ekadashi", "Ekadashi", None, "single", (), None)
    text = words.render_day(report(observances=(unclear,), claims_withheld=False), date(2026, 11, 21))
    assert "no clear day" in text and "local panchang may differ" in text


def test_a_checked_explanation_is_included_in_our_own_words():
    o = ekadashi("single", (), "A day many households fast.")
    assert "A day many households fast." in words.render_day(report(observances=(o,), claims_withheld=False),
                                                             date(2026, 11, 20))


def test_next_answer_cases():
    found = ekadashi("single", ())
    ok = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", found, True, False)
    assert words.render_next(ok) == "The next Ekadashi is Friday, 20 November 2026 in Pune."
    unverified = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", None, False, False)
    assert "not set up" in words.render_next(unverified)
    needs = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", None, False, True)
    assert "tradition" in words.render_next(needs)
    nothing = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", None, True, False)
    assert "could not find" in words.render_next(nothing)


def test_next_answer_names_the_alternate_day():
    ok = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", ekadashi(), True, False)
    lines = words.render_next(ok).splitlines()
    assert lines[0] == "The next Ekadashi is Friday, 20 November 2026 in Pune."
    assert lines[1].startswith("Some calendars place it on Saturday, 21 November 2026.")
    assert "local panchang may differ" in lines[1]


def test_about_answer_without_a_checked_entry_is_honest():
    assert "no checked source" in words.render_about("Ekadashi", []).lower()
    assert "Our own words." in words.render_about("Bharani", ["Our own words."])


def test_brief_is_plain_language_with_no_dasha_and_no_jargon():
    text = words.render_brief(datetime(2026, 11, 21, 7, 0), None, "Pune", report())
    assert text.startswith("🌅 Good morning! Today is Saturday, 21 November 2026.")
    assert ("At sunrise: the Moon's lunar day (tithi) Shukla Dwadashi, until 04:57 on 22 Nov; "
            "the Moon's star (nakshatra) Uttara Bhadrapada, until 06:50.") in text
    assert "Tulu date: Jaarde 5" in text
    assert not DASHA_WORD.search(text) and "Rahu Kaala" not in text


def test_brief_names_the_avoid_window_without_promising_an_outcome():
    from samay.engine.daylight import RahuKaala

    start = datetime(2026, 11, 21, 9, 30, tzinfo=IST)
    rahu = RahuKaala(date(2026, 11, 21), start, start + timedelta(minutes=84), start, start)
    text = words.render_brief(datetime(2026, 11, 21, 7, 0), rahu, "Pune", None)
    assert text.splitlines()[1] == "Traditionally avoided for starting new things: 09:30 to 10:54 (called Rahu Kaala), Pune."
    for promise in ("auspicious", "inauspicious", "lucky", "unlucky", "will "):
        assert promise not in text.lower()


def test_brief_on_the_observance_day_and_on_its_alternate():
    on_day = words.render_brief(datetime(2026, 11, 20, 7, 0), None, "Pune",
                                report(observances=(ekadashi(),), claims_withheld=False))
    assert "Ekadashi: today." in on_day and "Saturday, 21 November 2026" in on_day
    alternate = words.render_brief(datetime(2026, 11, 21, 7, 0), None, "Pune",
                                   report(observances=(ekadashi(),), claims_withheld=False))
    assert "Ekadashi: some calendars keep it today" in alternate and "Friday, 20 November 2026" in alternate
    assert "Ekadashi: today." not in alternate and "no clear day" not in alternate


@needs_kernel
def test_day_answer_from_a_real_report():
    from samay import service
    from samay.engine.geo import Place

    pune = Place("pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458)
    text = words.render_day(service.panchang_report(pune, date(2026, 11, 21)), date(2026, 11, 21))
    assert "Tithi (the Moon's lunar day): Shukla Dwadashi, until 04:57 on 22 Nov." in text
    assert "Nakshatra (the Moon's star): Uttara Bhadrapada, until 06:50." in text
    assert "Sunrise 06:44, sunset 17:56." in text and "Tulu date: Jaarde 5" in text
    before = words.render_day(service.panchang_report(pune, date(2026, 11, 20)), date(2026, 11, 20))
    assert "Shukla Dashami" in before and not DASHA_WORD.search(before) and "Rahu" not in before


def test_a_nakshatra_note_is_shown_alone_without_date_wording():
    note = ObservanceDay("bharani", "Bharani", None, "single", (), "A description of the star's character.")
    r = report(observances=(note,), claims_withheld=False)
    for text in (words.render_day(r, date(2026, 11, 21)),
                 words.render_brief(datetime(2026, 11, 21, 7, 0), None, "Pune", r)):
        assert text.count("A description of the star's character.") == 1
        assert "Bharani:" not in text and words.NOTE_LOCAL not in text and "no clear day" not in text


def test_a_nakshatra_note_does_not_hide_that_observance_days_are_withheld():
    note = ObservanceDay("bharani", "Bharani", None, "single", (), "A description of the star's character.")
    assert words.NO_CLAIM in words.render_day(report(observances=(note,)), date(2026, 11, 21))


def test_a_dated_observance_does_not_add_the_withheld_line():
    assert words.NO_CLAIM not in words.render_day(report(observances=(ekadashi(),)), date(2026, 11, 20))


def test_a_tithi_that_ends_the_same_day_says_which_one_follows():
    import datetime as dt

    from samay import service
    from samay.engine.geo import Place

    # Pune, 20 Nov 2026: Dashami at sunrise, Ekadashi from 07:16.
    place = Place("pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458)
    text = words.render_day(service.panchang_report(place, dt.date(2026, 11, 20)), dt.date(2026, 11, 20))
    assert "Shukla Dashami, until 07:16, then Shukla Ekadashi from 07:16." in text
    # 21 Nov: Dwadashi runs past midnight, so nothing is added.
    later = words.render_day(service.panchang_report(place, dt.date(2026, 11, 21)), dt.date(2026, 11, 21))
    assert "then" not in later.splitlines()[1]
