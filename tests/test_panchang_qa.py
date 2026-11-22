from datetime import UTC, date, datetime

import pytest

from samay import panchang_qa as pq
from samay.engine.geo import Place
from samay.engine.paths import EPHEMERIS_PATH
from samay.render import panchang as words

PUNE = Place("pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458)
TODAY = date(2026, 11, 21)  # a Saturday
NOW = datetime(2026, 11, 21, 4, 0, tzinfo=UTC)


@pytest.mark.parametrize("text, kind, observance", [
    ("is today special?", "day", None),
    ("what's the tithi today", "day", None),
    ("is tomorrow auspicious", "day", None),
    ("when is the next Ekadashi?", "next", "ekadashi"),
    ("when will the next ekadashi be", "next", "ekadashi"),
    ("next pradosh", "next", "pradosha"),
    ("what is Ekadashi", "about", "ekadashi"),
    ("why is Purnima important", "about", "purnima"),
    ("when is amavasya", "next", "amavasya"),
    ("what is the panchang on 2026-12-04", "day", None),
    ("is it ekadashi today", "day", "ekadashi"),       # a named day and no "next/when": the day's own facts
    ("is tomorrow poornima?", "day", "purnima"),
    ("is ekadashi on 4 December 2026", "day", "ekadashi"),
    ("when is the next full moon", "next", "purnima"),  # two words joined make a compact alias
    ("next new moon", "next", "amavasya"),
    ("tell me about pradosha", "about", "pradosha"),
])
def test_questions_are_sorted(text, kind, observance):
    asked = pq.sort(text)
    assert (asked.kind, asked.observance) == (kind, observance)


@pytest.mark.parametrize("text", [
    "what is my nakshatra", "when was I born, what star", "tell me about Jupiter", "will Ekadashi bring me luck?",
    "is tomorrow a good day to buy shares", "hello",
    "what is my sign", "tithi of my birth", "what tithi was I born on", "is today lucky for me",
    "where is Saturn on ekadashi", "is the moon special today", "is today auspicious for jupiter",
    "is tomorrow bad for a wedding",
    "is today special for my chart",
])
def test_everything_else_is_left_to_the_existing_router(text):
    assert pq.sort(text) is None


@pytest.mark.parametrize("text", [
    "what is a new moonstone",     # "newmoon" only as a substring of the joined text
    "the pradoshams were long",    # a longer word that only starts with an alias
    "the full moonlight was nice",
    "unpradosh",
])
def test_aliases_match_whole_words_or_joined_words_only(text):
    asked = pq.sort(text)
    assert asked is None or asked.observance is None


@pytest.mark.parametrize("text, expected", [
    ("is today special", TODAY), ("is tomorrow auspicious", date(2026, 11, 22)),
    ("tithi on Monday", date(2026, 11, 23)), ("panchang 2026-12-04", date(2026, 12, 4)),
    ("panchang on 4 December 2026", date(2026, 12, 4)), ("panchang on 4th december 2026", date(2026, 12, 4)),
    ("panchang on december 4, 2026", date(2026, 12, 4)), ("panchang on december 4", date(2026, 12, 4)),
    ("panchang on 5 january", date(2027, 1, 5)),  # a day already past this year means next year's
    ("tithi on Saturday", date(2026, 11, 28)),     # the weekday it is now means the next one, a week ahead
    ("tithi yesterday", date(2026, 11, 20)),
])
def test_dates_are_resolved_in_the_places_own_day(text, expected):
    assert pq.resolve_when(pq.sort(text).when, TODAY) == expected


def test_a_weekday_asked_on_that_weekday_means_a_week_later():
    monday = date(2026, 11, 23)
    assert pq.resolve_when(pq.sort("panchang on monday").when, monday) == date(2026, 11, 30)


@pytest.mark.parametrize("text", [
    "panchang on 2026-13-01", "panchang on 31 February 2026", "tithi on february 30", "panchang 2026-02-29",
    "is ekadashi on 32 december",
])
def test_impossible_dates_do_not_crash_and_ask_which_day(text):
    asked = pq.sort(text)
    assert asked.kind == "day" and asked.when.kind == "bad"
    assert pq.answer(asked, PUNE, NOW) == words.WHICH_DATE


pytestmark_engine = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")


@pytestmark_engine
def test_a_day_question_gets_the_facts():
    reply = pq.answer(pq.sort("what is the tithi today"), PUNE, NOW)
    assert "Shukla Dwadashi" in reply and "Tulu date" in reply


@pytestmark_engine
def test_an_observance_named_with_a_day_gets_that_days_facts():
    reply = pq.answer(pq.sort("is it ekadashi today"), PUNE, NOW)
    assert "Saturday, 21 November 2026 in Pune" in reply and "Tithi" in reply and "Tulu date" in reply


@pytestmark_engine
def test_a_next_question_without_a_verified_rule_does_not_name_a_day():
    reply = pq.answer(pq.sort("when is the next Ekadashi"), PUNE, NOW)
    assert "not set up" in reply


@pytestmark_engine
def test_an_about_question_without_a_checked_entry_says_so():
    reply = pq.answer(pq.sort("what is Ekadashi"), PUNE, NOW)
    assert "no checked source" in reply.lower()


@pytestmark_engine
def test_far_future_dates_get_a_plain_refusal():
    reply = pq.answer(pq.sort("panchang on 2300-01-01"), PUNE, NOW)
    assert "1972 and 2150" in reply


@pytestmark_engine
@pytest.mark.parametrize("day, answered", [
    ("1971-12-31", False), ("1972-01-05", False),  # the first days of 1972 need positions from before it
    ("1972-06-01", True), ("2150-01-10", True),
    ("2150-01-19", False), ("2150-06-01", False),  # past the end of the planetary kernel
])
def test_the_edges_of_the_engines_range(day, answered):
    reply = pq.answer(pq.sort(f"panchang on {day}"), PUNE, NOW)
    assert (reply != words.TOO_FAR) is answered
    if answered:
        assert "Tulu date" in reply
