from datetime import UTC, date, datetime

import pytest

from samay import panchang_qa as pq
from samay.engine.geo import Place
from samay.engine.paths import EPHEMERIS_PATH
from samay.render import panchang as words

PUNE = Place(
    "pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458
)
TODAY = date(2026, 11, 21)  # a Saturday
NOW = datetime(2026, 11, 21, 4, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "text, kind, observance",
    [
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
        (
            "is it ekadashi today",
            "day",
            "ekadashi",
        ),  # a named day and no "next/when": the day's own facts
        ("is tomorrow poornima?", "day", "purnima"),
        ("is ekadashi on 4 December 2026", "day", "ekadashi"),
        (
            "when is the next full moon",
            "next",
            "purnima",
        ),  # two words joined make a compact alias
        ("next new moon", "next", "amavasya"),
        ("tell me about pradosha", "about", "pradosha"),
        ("what is the nakshatra today", "day", None),
        ("today's karana", "day", None),
        ("nakshatra tomorrow", "day", None),
        ("which nakshatras are there on 2026-12-04", "day", None),
    ],
)
def test_questions_are_sorted(text, kind, observance):
    asked = pq.sort(text)
    assert (asked.kind, asked.observance) == (kind, observance)


@pytest.mark.parametrize(
    "text",
    [
        "what is my nakshatra",
        "when was I born, what star",
        "tell me about Jupiter",
        "will Ekadashi bring me luck?",
        "is tomorrow a good day to buy shares",
        "hello",
        "what is my sign",
        "tithi of my birth",
        "what tithi was I born on",
        "is today lucky for me",
        "where is Saturn on ekadashi",
        "is the moon special today",
        "is today auspicious for jupiter",
        "is tomorrow bad for a wedding",
        "is today special for my chart",
        "my star",
        "which nakshatra was I born under",
        "what is my karana",
        "yoga today",
        "what is a nakshatra?",
        "what is a karana",
        "list the nakshatras",  # the idea, not a day: qa.py
    ],
)
def test_everything_else_is_left_to_the_existing_router(text):
    assert pq.sort(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "what is a new moonstone",  # "newmoon" only as a substring of the joined text
        "the pradoshams were long",  # a longer word that only starts with an alias
        "the full moonlight was nice",
        "unpradosh",
    ],
)
def test_aliases_match_whole_words_or_joined_words_only(text):
    asked = pq.sort(text)
    assert asked is None or asked.observance is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("is today special", TODAY),
        ("is tomorrow auspicious", date(2026, 11, 22)),
        ("tithi on Monday", date(2026, 11, 23)),
        ("panchang 2026-12-04", date(2026, 12, 4)),
        ("panchang on 4 December 2026", date(2026, 12, 4)),
        ("panchang on 4th december 2026", date(2026, 12, 4)),
        ("panchang on december 4, 2026", date(2026, 12, 4)),
        ("panchang on december 4", date(2026, 12, 4)),
        (
            "panchang on 5 january",
            date(2027, 1, 5),
        ),  # a day already past this year means next year's
        (
            "tithi on Saturday",
            date(2026, 11, 28),
        ),  # the weekday it is now means the next one, a week ahead
        ("tithi yesterday", date(2026, 11, 20)),
    ],
)
def test_dates_are_resolved_in_the_places_own_day(text, expected):
    assert pq.resolve_when(pq.sort(text).when, TODAY) == expected


def test_a_weekday_asked_on_that_weekday_means_a_week_later():
    monday = date(2026, 11, 23)
    assert pq.resolve_when(pq.sort("panchang on monday").when, monday) == date(
        2026, 11, 30
    )


@pytest.mark.parametrize(
    "text",
    [
        "panchang on 2026-13-01",
        "panchang on 31 February 2026",
        "tithi on february 30",
        "panchang 2026-02-29",
        "is ekadashi on 32 december",
    ],
)
def test_impossible_dates_do_not_crash_and_ask_which_day(text):
    asked = pq.sort(text)
    assert asked.kind == "day" and asked.when.kind == "bad"
    assert pq.answer(asked, PUNE, NOW) == words.WHICH_DATE


pytestmark_engine = pytest.mark.skipif(
    not EPHEMERIS_PATH.exists(), reason="ephemeris file not present"
)


@pytestmark_engine
def test_a_day_question_gets_the_facts():
    reply = pq.answer(pq.sort("what is the tithi today"), PUNE, NOW)
    assert "Shukla Dwadashi" in reply and "Tulu date" in reply


@pytestmark_engine
def test_an_observance_named_with_a_day_gets_that_days_facts():
    reply = pq.answer(pq.sort("is it ekadashi today"), PUNE, NOW)
    assert (
        "Saturday, 21 November 2026 in Pune" in reply
        and "Tithi" in reply
        and "Tulu date" in reply
    )


@pytestmark_engine
def test_a_next_question_names_the_day_from_the_shipped_profile():
    reply = pq.answer(pq.sort("when is the next Ekadashi"), PUNE, NOW)
    assert "Friday, 04 December 2026" in reply and "not set up" not in reply


@pytestmark_engine
def test_a_next_question_without_a_verified_rule_does_not_name_a_day(
    tmp_path, monkeypatch
):
    import yaml

    from samay import service
    from samay.engine import panchang_profile
    from samay.engine.paths import PROFILES_DIR

    raw = yaml.safe_load((PROFILES_DIR / "panchang-family.yaml").read_text())
    for spec in raw["observances"].values():
        spec["verified"] = False
    (tmp_path / "panchang-family.yaml").write_text(yaml.safe_dump(raw))
    monkeypatch.setattr(service, "PANCHANG_PROFILES_DIR", tmp_path)
    panchang_profile.load_panchang_profile.cache_clear()
    try:
        reply = pq.answer(pq.sort("when is the next Ekadashi"), PUNE, NOW)
    finally:
        panchang_profile.load_panchang_profile.cache_clear()
    assert "not set up" in reply and "2026" not in reply


@pytestmark_engine
def test_an_about_question_without_a_checked_entry_says_so():
    reply = pq.answer(pq.sort("what is Ekadashi"), PUNE, NOW)
    assert "no checked source" in reply.lower()


@pytestmark_engine
def test_an_about_question_with_a_checked_entry_gives_its_text():
    from samay.engine import entries

    reply = pq.answer(pq.sort("what is Pradosha"), PUNE, NOW)
    assert reply == entries.answers_for("observance:pradosha")[0].english


@pytestmark_engine
def test_far_future_dates_get_a_plain_refusal():
    reply = pq.answer(pq.sort("panchang on 2300-01-01"), PUNE, NOW)
    assert "1972 and 2150" in reply


@pytestmark_engine
@pytest.mark.parametrize(
    "day, answered",
    [
        ("1971-12-31", False),
        ("1972-01-05", False),  # the first days of 1972 need positions from before it
        ("1972-06-01", True),
        ("2150-01-10", True),
        ("2150-01-19", False),
        ("2150-06-01", False),  # past the end of the planetary kernel
    ],
)
def test_the_edges_of_the_engines_range(day, answered):
    reply = pq.answer(pq.sort(f"panchang on {day}"), PUNE, NOW)
    assert (reply != words.TOO_FAR) is answered
    if answered:
        assert "Tulu date" in reply


def test_a_nakshatra_question_is_asked_for_the_right_day():
    assert pq.resolve_when(pq.sort("nakshatra tomorrow").when, TODAY) == date(
        2026, 11, 22
    )


@pytestmark_engine
def test_a_nakshatra_question_gets_the_days_facts():
    reply = pq.answer(pq.sort("what is the nakshatra today"), PUNE, NOW)
    assert (
        "Nakshatra (the Moon's star)" in reply
        and "Karana" in reply
        and "Tulu date" in reply
    )


@pytest.mark.parametrize(
    "text", ["when is the next pradosham", "what is Pradosham", "next pradosh vratham"]
)
def test_south_indian_spellings_of_pradosha_are_understood(text):
    assert pq.sort(text).observance == "pradosha"


# --- lists of observance days over a range ------------------------------------------------------

SUNDAY = date(2026, 11, 22)  # the week of Mon 16 to Sun 22 November 2026


@pytest.mark.parametrize(
    "text, names, first, last",
    [
        (
            "list all auspicious days this week",
            (),
            date(2026, 11, 16),
            date(2026, 11, 22),
        ),
        ("list observance days next week", (), date(2026, 11, 23), date(2026, 11, 29)),
        ("auspicious days this month", (), date(2026, 11, 1), date(2026, 11, 30)),
        (
            "list all auspicious days next month",
            (),
            date(2026, 12, 1),
            date(2026, 12, 31),
        ),
        ("all auspicious days in December", (), date(2026, 12, 1), date(2026, 12, 31)),
        ("list auspicious days in march 2027", (), date(2027, 3, 1), date(2027, 3, 31)),
        ("auspicious days for 2027", (), date(2027, 1, 1), date(2027, 12, 31)),
        ("auspicious 2027", (), date(2027, 1, 1), date(2027, 12, 31)),
        (
            "list all observance days this year",
            (),
            date(2026, 1, 1),
            date(2026, 12, 31),
        ),
        ("festival calendar next year", (), date(2027, 1, 1), date(2027, 12, 31)),
        (
            "fasting days in the next 30 days",
            (),
            date(2026, 11, 22),
            date(2026, 12, 21),
        ),
        (
            "list the auspicious days in the coming days",
            (),
            date(2026, 11, 22),
            date(2026, 12, 21),
        ),
        ("ekadashi dates in 2027", ("ekadashi",), date(2027, 1, 1), date(2027, 12, 31)),
        ("pradosha this month", ("pradosha",), date(2026, 11, 1), date(2026, 11, 30)),
        (
            "when are amavasya days in January",
            ("amavasya",),
            date(2027, 1, 1),
            date(2027, 1, 31),
        ),
        (
            "when is amavasya in november",
            ("amavasya",),
            date(2026, 11, 1),
            date(2026, 11, 30),
        ),  # this month is this year's
        (
            "list all ekadashi and pradosha days in December 2026",
            ("ekadashi", "pradosha"),
            date(2026, 12, 1),
            date(2026, 12, 31),
        ),
        ("full moon days in 2027", ("purnima",), date(2027, 1, 1), date(2027, 12, 31)),
        (
            "new moon dates next month",
            ("amavasya",),
            date(2026, 12, 1),
            date(2026, 12, 31),
        ),
        (
            "list pradosham dates for may 2027",
            ("pradosha",),
            date(2027, 5, 1),
            date(2027, 5, 31),
        ),
        ("ekadashi in may", ("ekadashi",), date(2027, 5, 1), date(2027, 5, 31)),
        (
            "list ekadashi",
            ("ekadashi",),
            date(2026, 11, 22),
            date(2026, 12, 21),
        ),  # "list" alone: the coming days
    ],
)
def test_list_questions_are_sorted_and_their_range_resolved(text, names, first, last):
    asked = pq.sort(text)
    assert asked.kind == "list" and asked.names == names
    assert asked.observance == (names[0] if names else None)
    assert pq.resolve_range(asked.when, SUNDAY) == (first, last)


@pytest.mark.parametrize(
    "text",
    [
        "what will this week be like",
        "how is my year looking",
        "list my dashas for 2027",
        "planets this month",
        "is 2027 a good year",
        "lucky days this month",
        "best days next week",
        "list all days for my birthday in 2027",
        "where is the moon this week",
        "will next year bring money",
        "hello this week",
    ],
)
def test_range_questions_that_are_not_about_observances_are_left_alone(text):
    assert pq.sort(text) is None


@pytest.mark.parametrize(
    "text, kind",
    [
        (
            "what may happen to me",
            None,
        ),  # "may" is a month only with a year or after in/for/of
        ("when is the next ekadashi", "next"),  # no range: the next one, as before
        ("is it ekadashi today", "day"),
        ("panchang on 4 December 2026", "day"),  # a single date is a day, not a month
        ("what is Ekadashi", "about"),
        ("list the nakshatras", None),
    ],
)
def test_questions_without_a_range_keep_their_old_kind(text, kind):
    asked = pq.sort(text)
    assert (asked.kind if asked else None) == kind


@pytest.mark.parametrize(
    "today, first, last",
    [
        (
            date(2026, 11, 23),
            date(2026, 11, 23),
            date(2026, 11, 29),
        ),  # Monday: the week starts today
        (
            date(2026, 11, 29),
            date(2026, 11, 23),
            date(2026, 11, 29),
        ),  # Sunday: the week ends today
        (
            date(2027, 1, 1),
            date(2026, 12, 28),
            date(2027, 1, 3),
        ),  # a week across the new year
    ],
)
def test_weeks_start_on_monday(today, first, last):
    assert pq.resolve_range(pq.sort("ekadashi this week").when, today) == (first, last)


def test_next_month_in_december_is_january_of_the_next_year():
    assert pq.resolve_range(
        pq.sort("pradosha next month").when, date(2026, 12, 15)
    ) == (date(2027, 1, 1), date(2027, 1, 31))


def test_a_range_over_366_days_is_too_long():
    asked = pq.sort("list ekadashi dates in the next 400 days")
    assert pq.resolve_range(asked.when, SUNDAY) == (SUNDAY, date(2027, 12, 26))
    assert (
        pq.answer(asked, PUNE, datetime(2026, 11, 22, 4, tzinfo=UTC)) == words.TOO_LONG
    )


def test_only_long_lists_are_slow():
    now = datetime(2026, 11, 22, 4, tzinfo=UTC)
    assert not pq.is_slow(pq.sort("ekadashi this month"), PUNE, now)
    assert pq.is_slow(pq.sort("ekadashi dates in 2027"), PUNE, now)
    assert not pq.is_slow(pq.sort("when is the next ekadashi"), PUNE, now)


@pytestmark_engine
def test_a_list_far_outside_the_engines_range_is_refused():
    assert pq.answer(pq.sort("ekadashi dates in 2300"), PUNE, NOW) == words.TOO_FAR


@pytestmark_engine
def test_a_list_question_gets_the_days_in_the_range():
    reply = pq.answer(
        pq.sort("list all ekadashi and pradosha days in December 2026"), PUNE, NOW
    )
    assert (
        reply.splitlines()[0]
        == f"Ekadashi and Pradosha days from Tue 1 Dec to Thu 31 Dec 2026 in {PUNE.label}"
    )
    assert (
        "Fri 4 Dec: Ekadashi" in reply
        and "Purnima" not in reply
        and "Amavasya" not in reply
    )
