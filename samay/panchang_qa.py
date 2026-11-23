"""Panchang questions: a table-driven sorter and the answer. A new observance is a row in OBSERVANCES, not a new
parsing path. Anything about the person's own chart, a planet, an outcome, or with no panchang word is left to qa.py."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from . import service
from .engine.ephemeris import EPHEMERIS_END, UTC_LEAP_SECONDS_FROM
from .engine.errors import OutOfEphemerisRange
from .render import panchang as words

# Aliases match a whole word, or two neighbouring words joined ("full moon" -> "fullmoon"), never a substring.
OBSERVANCES = {
    "ekadashi": ("ekadashi", "ekadasi", "ekadashis"),
    "pradosha": ("pradosha", "pradosh", "pradoshas", "pradosham", "pradoshan"),
    "purnima": ("purnima", "poornima", "pournami", "fullmoon"),
    "amavasya": ("amavasya", "amavasai", "newmoon"),
    "sankashti": ("sankashti", "sankasthi", "sankata", "sankatahara", "sankashta"),
}
LABELS = {
    "ekadashi": "Ekadashi",
    "pradosha": "Pradosha",
    "purnima": "Purnima",
    "amavasya": "Amavasya",
    "sankashti": "Sankashti Chaturthi",
}
DAY_WORDS = ("tithi", "panchang", "panchanga", "panchangam")
# A day only when one is named ("nakshatra tomorrow"); alone ("what is a nakshatra") qa.py answers from its sources.
# Not "yoga": too often the exercise.
TIMED_DAY_WORDS = ("nakshatra", "nakshatras", "karana")
SPECIAL_WORDS = (
    "special",
    "auspicious",
    "inauspicious",
    "festival",
    "fasting",
    "vrat",
    "vratam",
)
NEXT_WORDS = ("when", "next", "upcoming")
# With a range ("this month", "in 2027"), any of these, an observance or a SPECIAL_WORDS word asks for a list of days.
LIST_WORDS = ("list", "all", "dates", "days", "calendar", "observance", "observances")
LIST_MAX_DAYS = 366
COMING_DAYS = 30  # "the coming days", or "list" with no range
SLOW_DAYS = 90  # a list longer than this gets "one moment" first
ABOUT_WORDS = (
    "what",
    "why",
    "mean",
    "meaning",
    "important",
    "importance",
    "significance",
    "about",
    "explain",
)
PERSONAL_WORDS = (
    "my",
    "mine",
    "born",
    "birth",
    "birthday",
)  # a question about the person's own chart
CHART_WORDS = (
    "planet",
    "planets",
    "graha",
    "grahas",
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
    "rahu",
    "ketu",
    "surya",
    "chandra",
    "shani",
    "guru",
    "chart",
    "kundli",
    "kundali",
    "horoscope",
    "lagna",
    "ascendant",
    "dasha",
    "sign",
    "rashi",
    "zodiac",
    "house",
)
OUTCOME_WORDS = (
    "luck",
    "lucky",
    "unlucky",
    "fortune",
    "bring",
    "good",
    "bad",
    "best",
    "favourable",
    "favorable",
    "should",
    "buy",
    "sell",
    "shares",
    "profit",
    "result",
    "success",
    "money",
    "invest",
    "wedding",
    "marriage",
)
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_WORD = re.compile(r"[a-z]+")
_MONTH = "|".join(MONTHS)
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b(?:,?\s+(\d{{4}})\b)?")
_MONTH_DAY = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?")
# Ranges, tried in this order. "may" and "march" are months only with a year or after in/for/of/during.
_N_DAYS = re.compile(r"\b(?:next|coming|upcoming)\s+(\d{1,4})\s+days\b")
_COMING_DAYS = re.compile(r"\b(?:the\s+)?(?:coming|upcoming)\s+days\b")
_MONTH_YEAR = re.compile(rf"\b({_MONTH})\s+(\d{{4}})\b")
_MONTH_ALONE = re.compile(rf"(?:\b(in|for|of|during)\s+)?\b({_MONTH})\b")
_RELATIVE = re.compile(r"\b(this|next|coming)\s+(week|month|year)\b")
_YEAR = re.compile(r"\b(\d{4})\b")


@dataclass(frozen=True)
class When:
    kind: str  # today | tomorrow | yesterday | weekday | date | monthday (no year given) | bad (an impossible date)
    value: object = None  # a weekday index, a date, or (month, day)


@dataclass(frozen=True)
class Asked:
    kind: str  # day | next | about | list
    observance: str | None
    when: When  # for a list: week, month, year (value: offset), named_month ((month, year or None)), year_number, days
    names: tuple[str, ...] = ()  # for a list: the observances asked about, none meaning all


def _dated(year: int | None, month: int, day: int) -> When:
    try:
        if year is None:
            date(2000, month, day)  # a leap year, so 29 February is possible
            return When("monthday", (month, day))
        return When("date", date(year, month, day))
    except ValueError:
        return When("bad")


def _when(text: str, found: list[str]) -> When:
    if m := _ISO.search(text):
        return _dated(int(m[1]), int(m[2]), int(m[3]))
    if m := _DAY_MONTH.search(text):
        return _dated(int(m[3]) if m[3] else None, MONTHS.index(m[2]) + 1, int(m[1]))
    if m := _MONTH_DAY.search(text):
        return _dated(int(m[3]) if m[3] else None, MONTHS.index(m[1]) + 1, int(m[2]))
    for word in ("tomorrow", "yesterday"):
        if word in found:
            return When(word)
    for i, name in enumerate(WEEKDAYS):
        if name in found:
            return When("weekday", i)
    return When("today")


def _observances(found: list[str]) -> tuple[str, ...]:
    pieces = set(found) | {a + b for a, b in pairwise(found)}
    return tuple(name for name, aliases in OBSERVANCES.items() if pieces.intersection(aliases))


def _span(text: str) -> tuple[When, str] | None:
    """The range a question names, and the text left once it is taken out (so "days" in "next 30 days" does not also
    ask for a list). A single date ("4 December 2026") is a day, not a range."""
    if _ISO.search(text) or _DAY_MONTH.search(text) or _MONTH_DAY.search(text):
        return None
    if m := _N_DAYS.search(text):
        when = When("days", int(m[1]))
    elif m := _COMING_DAYS.search(text):
        when = When("days", COMING_DAYS)
    elif m := _MONTH_YEAR.search(text):
        when = When("named_month", (MONTHS.index(m[1]) + 1, int(m[2])))
    elif (m := _MONTH_ALONE.search(text)) and (m[1] or m[2] not in ("may", "march")):
        when = When("named_month", (MONTHS.index(m[2]) + 1, None))
    elif m := _RELATIVE.search(text):
        when = When(m[2], 0 if m[1] == "this" else 1)
    elif m := _YEAR.search(text):
        when = When("year_number", int(m[1]))
    else:
        return None
    return when, text[: m.start()] + " " + text[m.end() :]


def sort(text: str) -> Asked | None:
    lowered = text.casefold()
    found = _WORD.findall(lowered)
    # "moon" in "full moon" or "new moon" names the day, not the planet
    chart = [
        w
        for i, w in enumerate(found)
        if w in CHART_WORDS and not (w == "moon" and i and found[i - 1] in ("full", "new"))
    ]
    if chart or any(w in PERSONAL_WORDS or w in OUTCOME_WORDS for w in found):
        return None
    names = _observances(found)
    observance = names[0] if names else None
    span = _span(lowered)
    rest = _WORD.findall(span[1]) if span else found
    listed = any(w in LIST_WORDS or w in SPECIAL_WORDS for w in rest)
    if span and (names or listed):
        return Asked("list", observance, span[0], names)
    if "list" in found and (
        names or any(w in SPECIAL_WORDS or w in ("observance", "observances") for w in found)
    ):
        return Asked("list", observance, When("days", COMING_DAYS), names)
    when = _when(lowered, found)
    timed = "today" in found or when.kind != "today"
    if observance:
        if any(w in NEXT_WORDS for w in found):
            return Asked("next", observance, when)
        if timed:  # "is it Ekadashi today": that day's own facts
            return Asked("day", observance, when)
        if any(w in ABOUT_WORDS for w in found):
            return Asked("about", observance, when)
        return Asked("next", observance, when)
    if any(w in DAY_WORDS for w in found) or (
        timed and any(w in SPECIAL_WORDS or w in TIMED_DAY_WORDS for w in found)
    ):
        return Asked("day", None, when)
    return None


def resolve_when(when: When, today: date) -> date:
    if when.kind == "date":
        return when.value
    if when.kind == "monthday":  # the next time that day comes round (29 February: the next leap year)
        month, day = when.value
        for year in range(today.year, today.year + 9):
            try:
                found = date(year, month, day)
            except ValueError:
                continue
            if found >= today:
                return found
    if when.kind == "tomorrow":
        return today + timedelta(days=1)
    if when.kind == "yesterday":
        return today - timedelta(days=1)
    if when.kind == "weekday":  # the day it is now means the same day next week
        return today + timedelta(days=(when.value - today.weekday()) % 7 or 7)
    return today


def resolve_range(when: When, today: date) -> tuple[date, date]:
    """First and last local day of a list's range. Weeks run Monday to Sunday; a month named without a year is the
    next time it comes round, this month included."""
    if when.kind == "days":
        return today, today + timedelta(days=when.value - 1)
    if when.kind == "week":
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=when.value)
        return monday, monday + timedelta(days=6)
    if when.kind in ("year", "year_number"):
        year = today.year + when.value if when.kind == "year" else when.value
        return date(year, 1, 1), date(year, 12, 31)
    if when.kind == "month":
        month, year = today.month + when.value, today.year
        if month > 12:
            month, year = month - 12, year + 1
    else:
        month, year = when.value
        if year is None:
            year = today.year if month >= today.month else today.year + 1
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return date(year, month, 1), following - timedelta(days=1)


def is_slow(asked: Asked, place, now: datetime) -> bool:
    """True for a list long enough that the bot should say "one moment" before working it out."""
    if asked.kind != "list":
        return False
    first, last = resolve_range(asked.when, now.astimezone(ZoneInfo(place.tz)).date())
    return SLOW_DAYS < (last - first).days + 1 <= LIST_MAX_DAYS


def _answer_list(asked: Asked, place, today: date) -> str:
    first, last = resolve_range(asked.when, today)
    if not (UTC_LEAP_SECONDS_FROM.date() <= first and last <= EPHEMERIS_END.date()):
        return words.TOO_FAR
    return words.render_list(service.observance_list_report(place, first, last, asked.names))


def answer(asked: Asked, place, now: datetime) -> str:
    today = now.astimezone(ZoneInfo(place.tz)).date()
    try:
        if asked.kind == "list":
            return _answer_list(asked, place, today)
        if asked.kind == "about":
            return words.render_about(
                LABELS[asked.observance],
                service.observance_explanation(asked.observance),
                service.observance_care_notes(asked.observance),
            )
        if asked.kind == "next":
            return words.render_next(service.next_observance_report(place, asked.observance, today))
        if asked.when.kind == "bad":
            return words.WHICH_DATE
        day = resolve_when(asked.when, today)
        # The engine's own range; the first and last days inside it can still need positions outside it (caught below).
        if not UTC_LEAP_SECONDS_FROM.date() <= day <= EPHEMERIS_END.date():
            return words.TOO_FAR
        report = service.panchang_report(place, day)
        return words.NO_SUN.format(place=place.label) if report is None else words.render_day(report, day)
    except OutOfEphemerisRange:
        return words.TOO_FAR
