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
    base = {
        "place_label": "Pune",
        "tz": "Asia/Kolkata",
        "facts": Facts,
        "tulu": Tulu,
        "cutoff": "sunset",
        "observances": (),
        "needs_sampradaya": False,
        "claims_withheld": True,
    }
    base.update(changes)
    return PanchangReport(**base)


def ekadashi(
    kind="kshaya",
    alternates=((date(2026, 11, 21), "kshaya and madhva convention"),),
    explanation=None,
):
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
    assert (
        "Shukla Dwadashi, until 23:27, then Shukla Trayodashi from 23:27." in text
        and "Uttara Bhadrapada, until 01:20." in text
    )


def test_unverified_rules_say_plainly_that_no_observance_day_is_named():
    assert "not named" in words.render_day(report(), date(2026, 11, 21)).lower()


def test_missing_tradition_asks_for_it():
    assert "tradition" in words.render_day(report(needs_sampradaya=True), date(2026, 11, 21)).lower()


def test_an_observance_day_shows_its_alternate_and_a_local_panchang_note():
    text = words.render_day(report(observances=(ekadashi(),), claims_withheld=False), date(2026, 11, 20))
    assert (
        "Ekadashi: today." in text
        and "Saturday, 21 November 2026" in text
        and "local panchang may differ" in text
    )


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
    assert "A day many households fast." in words.render_day(
        report(observances=(o,), claims_withheld=False), date(2026, 11, 20)
    )


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
    assert (
        "At sunrise: the Moon's lunar day (tithi) Shukla Dwadashi, until 04:57 on 22 Nov; "
        "the Moon's star (nakshatra) Uttara Bhadrapada, until 06:50."
    ) in text
    assert "Tulu date: Jaarde 5" in text
    assert not DASHA_WORD.search(text) and "Rahu Kaala" not in text


def test_brief_names_the_avoid_window_without_promising_an_outcome():
    from samay.engine.daylight import RahuKaala

    start = datetime(2026, 11, 21, 9, 30, tzinfo=IST)
    rahu = RahuKaala(date(2026, 11, 21), start, start + timedelta(minutes=84), start, start)
    text = words.render_brief(datetime(2026, 11, 21, 7, 0), rahu, "Pune", None)
    assert (
        text.splitlines()[1]
        == "Traditionally avoided for starting new things: 09:30 to 10:54 (called Rahu Kaala), Pune."
    )
    for promise in ("auspicious", "inauspicious", "lucky", "unlucky", "will "):
        assert promise not in text.lower()


def test_brief_on_the_observance_day_and_on_its_alternate():
    on_day = words.render_brief(
        datetime(2026, 11, 20, 7, 0),
        None,
        "Pune",
        report(observances=(ekadashi(),), claims_withheld=False),
    )
    assert "Ekadashi: today." in on_day and "Saturday, 21 November 2026" in on_day
    alternate = words.render_brief(
        datetime(2026, 11, 21, 7, 0),
        None,
        "Pune",
        report(observances=(ekadashi(),), claims_withheld=False),
    )
    assert "Ekadashi: some calendars keep it today" in alternate and "Friday, 20 November 2026" in alternate
    assert "Ekadashi: today." not in alternate and "no clear day" not in alternate


@needs_kernel
def test_day_answer_from_a_real_report():
    from samay import service
    from samay.engine.geo import Place

    pune = Place(
        "pune",
        "Pune",
        "IN",
        "Maharashtra",
        None,
        18.5196,
        73.8553,
        "Asia/Kolkata",
        3124458,
    )
    text = words.render_day(service.panchang_report(pune, date(2026, 11, 21)), date(2026, 11, 21))
    assert "Tithi (the Moon's lunar day): Shukla Dwadashi, until 04:57 on 22 Nov." in text
    assert "Nakshatra (the Moon's star): Uttara Bhadrapada, until 06:50." in text
    assert "Sunrise 06:45, sunset 17:55." in text and "Tulu date: Jaarde 5" in text
    before = words.render_day(service.panchang_report(pune, date(2026, 11, 20)), date(2026, 11, 20))
    assert "Shukla Dashami" in before and not DASHA_WORD.search(before) and "Rahu" not in before


def test_a_nakshatra_note_is_shown_alone_without_date_wording():
    note = ObservanceDay(
        "bharani",
        "Bharani",
        None,
        "single",
        (),
        "A description of the star's character.",
    )
    r = report(observances=(note,), claims_withheld=False)
    for text in (
        words.render_day(r, date(2026, 11, 21)),
        words.render_brief(datetime(2026, 11, 21, 7, 0), None, "Pune", r),
    ):
        assert text.count("A description of the star's character.") == 1
        assert "Bharani:" not in text and words.NOTE_LOCAL not in text and "no clear day" not in text


def test_a_nakshatra_note_does_not_hide_that_observance_days_are_withheld():
    note = ObservanceDay(
        "bharani",
        "Bharani",
        None,
        "single",
        (),
        "A description of the star's character.",
    )
    assert words.NO_CLAIM in words.render_day(report(observances=(note,)), date(2026, 11, 21))


def test_a_dated_observance_does_not_add_the_withheld_line():
    assert words.NO_CLAIM not in words.render_day(report(observances=(ekadashi(),)), date(2026, 11, 20))


def test_a_tithi_that_ends_the_same_day_says_which_one_follows():
    import datetime as dt

    from samay import service
    from samay.engine.geo import Place

    # Pune, 20 Nov 2026: Dashami at sunrise, Ekadashi from 07:16.
    place = Place(
        "pune",
        "Pune",
        "IN",
        "Maharashtra",
        None,
        18.5196,
        73.8553,
        "Asia/Kolkata",
        3124458,
    )
    text = words.render_day(service.panchang_report(place, dt.date(2026, 11, 20)), dt.date(2026, 11, 20))
    assert "Shukla Dashami, until 07:16, then Shukla Ekadashi from 07:16." in text
    # 21 Nov: Dwadashi runs past midnight, so nothing is added.
    later = words.render_day(service.panchang_report(place, dt.date(2026, 11, 21)), dt.date(2026, 11, 21))
    assert "then" not in later.splitlines()[1]


# --- lists of observance days ------------------------------------------------------------------

from samay.models import ObservanceListReport


def listed(name, label, primary, alternates=()):
    return ObservanceDay(name, label, primary, "single", alternates, None)


def list_report(first, last, days=(), **changes):
    base = {
        "place_label": "Mangaluru",
        "tz": "Asia/Kolkata",
        "first": first,
        "last": last,
        "labels": ("Ekadashi", "Pradosha", "Purnima", "Amavasya"),
        "filtered": False,
        "days": tuple(days),
        "withheld": (),
        "needs_sampradaya": False,
        "too_long": False,
    }
    base.update(changes)
    return ObservanceListReport(**base)


WEEK = (date(2026, 11, 23), date(2026, 11, 29))


def test_a_list_has_a_header_one_line_per_date_and_counts():
    text = words.render_list(
        list_report(
            *WEEK,
            [
                listed("pradosha", "Pradosha", date(2026, 11, 27)),
                listed("purnima", "Purnima", date(2026, 11, 24)),
            ],
        )
    )
    lines = text.splitlines()
    assert lines[0] == "Observance days from Mon 23 Nov to Sun 29 Nov 2026 in Mangaluru"
    assert lines.index("Tue 24 Nov: Purnima") < lines.index("Fri 27 Nov: Pradosha")
    assert lines[-1] == "2 days: 1 Pradosha, 1 Purnima."
    assert "some calendars" not in text.lower()  # no alternate, so no note about them


def test_a_list_shows_alternates_and_one_note_about_local_panchangs():
    text = words.render_list(
        list_report(
            *WEEK,
            [
                listed(
                    "ekadashi",
                    "Ekadashi",
                    date(2026, 11, 23),
                    ((date(2026, 11, 24), "kshaya and madhva convention"),),
                ),
                listed(
                    "pradosha",
                    "Pradosha",
                    date(2026, 11, 25),
                    ((date(2026, 11, 26), "calculation"),),
                ),
            ],
        )
    )
    assert "Mon 23 Nov: Ekadashi (some calendars: Tue 24 Nov)" in text
    assert "Wed 25 Nov: Pradosha (some calendars: Thu 26 Nov)" in text
    assert text.count(words.NOTE_LIST) == 1 and "kshaya" not in text and "convention" not in text


def test_two_observances_on_one_date_share_its_line():
    day = date(2026, 11, 24)
    text = words.render_list(
        list_report(
            *WEEK,
            [listed("purnima", "Purnima", day), listed("pradosha", "Pradosha", day)],
        )
    )
    assert (
        "Tue 24 Nov: Purnima and Pradosha" in text
        and text.splitlines()[-1] == "1 day: 1 Pradosha, 1 Purnima."
    )


def test_a_day_whose_primary_is_outside_the_range_is_shown_only_as_some_calendars():
    text = words.render_list(
        list_report(
            *WEEK,
            [
                listed(
                    "ekadashi",
                    "Ekadashi",
                    date(2026, 11, 22),
                    ((date(2026, 11, 23), "kshaya"),),
                )
            ],
        )
    )
    assert "Mon 23 Nov: Ekadashi in some calendars (the day I use is Sun 22 Nov)" in text
    assert "0 days" not in text and text.splitlines()[-1] == words.NOTE_LIST  # counted only where its day is


def test_a_long_list_is_grouped_by_month():
    text = words.render_list(
        list_report(
            date(2026, 11, 22),
            date(2027, 1, 31),
            [
                listed("purnima", "Purnima", date(2026, 11, 24)),
                listed("ekadashi", "Ekadashi", date(2026, 12, 4)),
                listed("amavasya", "Amavasya", date(2027, 1, 7)),
            ],
        )
    )
    assert text.splitlines()[0] == "Observance days from Sun 22 Nov 2026 to Sun 31 Jan 2027 in Mangaluru"
    assert (
        "\n\nNovember 2026\nTue 24 Nov: Purnima" in text and "\n\nDecember 2026\nFri 4 Dec: Ekadashi" in text
    )
    assert "\n\nJanuary 2027\nThu 7 Jan: Amavasya" in text


def test_a_filtered_list_names_what_was_asked_and_an_empty_one_says_so():
    text = words.render_list(list_report(*WEEK, labels=("Ekadashi",), filtered=True))
    assert text == "No Ekadashi days fall between Mon 23 Nov and Sun 29 Nov 2026 in Mangaluru."
    assert words.render_list(list_report(*WEEK)).startswith("No observance days fall between")


def test_a_list_never_calls_a_day_good_or_lucky():
    text = words.render_list(list_report(*WEEK, [listed("purnima", "Purnima", date(2026, 11, 24))]))
    assert words.LIST_SCOPE in text
    assert not any(w in text.lower() for w in ("auspicious", "lucky", "favourable", "will bring"))


def test_a_list_says_why_days_are_missing():
    text = words.render_list(
        list_report(
            *WEEK,
            [listed("purnima", "Purnima", date(2026, 11, 24))],
            withheld=("Pradosha",),
            needs_sampradaya=True,
        )
    )
    assert "Pradosha" in text.split("Tue 24 Nov")[1] and "not set up from a checked source" in text
    assert words.NEED_TRADITION in text
    nothing = words.render_list(list_report(*WEEK, withheld=("Ekadashi", "Pradosha", "Purnima", "Amavasya")))
    assert "not set up from a checked source" in nothing and "Nov:" not in nothing
    assert words.render_list(list_report(*WEEK, too_long=True)) == words.TOO_LONG


def test_a_years_list_splits_between_lines_under_telegrams_limit():
    from samay.render.text import split_message

    first = date(2027, 1, 1)
    days = [
        listed(
            "ekadashi",
            "Ekadashi",
            first + timedelta(days=d),
            ((first + timedelta(days=d + 1), "x"),),
        )
        for d in range(0, 365, 2)
    ]
    text = words.render_list(list_report(first, date(2027, 12, 31), days))
    parts = split_message(text)
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)
    assert "\n".join(parts).replace("\n\n", "\n") == text.replace(
        "\n\n", "\n"
    )  # whole lines only, nothing lost
