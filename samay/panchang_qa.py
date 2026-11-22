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
    "pradosha": ("pradosha", "pradosh", "pradoshas"),
    "purnima": ("purnima", "poornima", "pournami", "fullmoon"),
    "amavasya": ("amavasya", "amavasai", "newmoon"),
}
LABELS = {"ekadashi": "Ekadashi", "pradosha": "Pradosha", "purnima": "Purnima", "amavasya": "Amavasya"}
DAY_WORDS = ("tithi", "panchang", "panchanga", "panchangam")
SPECIAL_WORDS = ("special", "auspicious", "inauspicious", "festival", "fasting", "vrat", "vratam")
NEXT_WORDS = ("when", "next", "upcoming")
ABOUT_WORDS = ("what", "why", "mean", "meaning", "important", "importance", "significance", "about", "explain")
PERSONAL_WORDS = ("my", "mine", "born", "birth", "birthday")  # a question about the person's own chart
CHART_WORDS = ("planet", "planets", "graha", "grahas", "sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn",
               "rahu", "ketu", "surya", "chandra", "shani", "guru", "chart", "kundli", "kundali", "horoscope", "lagna",
               "ascendant", "dasha", "sign", "rashi", "zodiac", "house")
OUTCOME_WORDS = ("luck", "lucky", "unlucky", "fortune", "bring", "good", "bad", "best", "favourable",
                 "favorable", "should", "buy", "sell", "shares", "profit", "result", "success", "money", "invest",
                 "wedding", "marriage")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
_WORD = re.compile(r"[a-z]+")
_MONTH = "|".join(MONTHS)
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b(?:,?\s+(\d{{4}})\b)?")
_MONTH_DAY = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?")


@dataclass(frozen=True)
class When:
    kind: str  # today | tomorrow | yesterday | weekday | date | monthday (no year given) | bad (an impossible date)
    value: object = None  # a weekday index, a date, or (month, day)


@dataclass(frozen=True)
class Asked:
    kind: str  # day | next | about
    observance: str | None
    when: When


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


def _observance(found: list[str]) -> str | None:
    pieces = set(found) | {a + b for a, b in pairwise(found)}
    return next((name for name, aliases in OBSERVANCES.items() if pieces.intersection(aliases)), None)


def sort(text: str) -> Asked | None:
    lowered = text.casefold()
    found = _WORD.findall(lowered)
    # "moon" in "full moon" or "new moon" names the day, not the planet
    chart = [w for i, w in enumerate(found) if w in CHART_WORDS
             and not (w == "moon" and i and found[i - 1] in ("full", "new"))]
    if chart or any(w in PERSONAL_WORDS or w in OUTCOME_WORDS for w in found):
        return None
    observance = _observance(found)
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
    if any(w in DAY_WORDS for w in found) or (timed and any(w in SPECIAL_WORDS for w in found)):
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


def answer(asked: Asked, place, now: datetime) -> str:
    today = now.astimezone(ZoneInfo(place.tz)).date()
    try:
        if asked.kind == "about":
            return words.render_about(LABELS[asked.observance], service.observance_explanation(asked.observance))
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
