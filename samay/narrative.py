"""Reading a free-form message about people ("my daughter Maya was born on 14 March 2015 at 6:30 in the morning in Pune,
and my son Arjun on 2 Nov 2018...") into structured details.

The local model only PROPOSES what it understood, as JSON. Everything it returns is validated here before use:
dates and times must parse, a year the model produced must actually appear in the message, text is cleaned and
bounded, and the person is always shown a summary to confirm. Nothing the model says is treated as fact.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import narrate
from .engine.errors import SamayError
from .service import parse_clock, parse_date
from .subject import MAX_NAME, MAX_RELATION, clean

MAX_PEOPLE_PER_MESSAGE = 6
MAX_PLACE = 80
MAX_NARRATIVE_CHARS = 1500
MAX_QUESTION = 300

EXTRACT_SYSTEM = (
    "You read a message in which someone describes people and their birth details, and you reply with ONE JSON "
    'object and nothing else. Schema: {"people": [{"name": str, "relation": str, "date": "YYYY-MM-DD", '
    '"time": "HH:MM", "time_certain": bool, "place": str}], "question": str, "about": str}. '
    "Rules: one entry per person described. Use an empty string for anything the message does not state; never "
    'guess or invent. "relation" is how the person relates to the writer (daughter, son, wife, husband, mother, '
    'father, friend...) or empty. "time" is 24-hour HH:MM, and time_certain is true only if the message makes '
    "morning or evening clear (am/pm, 'in the evening', a 24-hour time); if it does not, give the time as written "
    'and set time_certain to false. "place" is the birthplace as written, with the country if given. '
    '"question" is what the writer wants to know, in their own words, or empty. "about" is the name of the '
    "person the question is about, or empty."
)


@dataclass(frozen=True)
class Mentioned:
    name: str = ""
    relation: str = ""
    date_text: str = ""  # YYYY-MM-DD, validated, or ""
    time_text: str = ""  # HH:MM, validated, or ""
    ask_ampm: tuple[int, int] | None = None  # (hour, minute) as written, when morning or evening is unclear
    place_text: str = ""


@dataclass(frozen=True)
class Extraction:
    people: tuple[Mentioned, ...]
    question: str = ""
    about: str = ""


def _text(value: object, limit: int) -> str:
    return clean(value, limit) if isinstance(value, str) else ""


def _date(value: str, narrative: str) -> str:
    """A validated ISO date, or "". A year the model produced must appear in the message, or it was invented."""
    if not value:
        return ""
    try:
        day = parse_date(value)
    except SamayError:
        return ""
    return day.strftime("%Y-%m-%d") if str(day.year) in narrative else ""


def _time(value: str, certain: bool) -> tuple[str, tuple[int, int] | None]:
    """(HH:MM, None) when the time is known, ("", (hour, minute)) when am/pm must be asked, ("", None) if unusable."""
    if not value:
        return "", None
    try:
        clock = parse_clock(value)
    except SamayError:
        return "", None
    if clock.ambiguous and not certain:
        return "", (clock.hour, clock.minute)
    return f"{clock.hour:02d}:{clock.minute:02d}", None


def parse_extraction(reply: str, narrative: str) -> Extraction | None:
    """The model's reply as validated details, or None if it is not usable JSON or names nobody."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        raw = json.loads(reply[start : end + 1])
    except ValueError:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("people"), list):
        return None
    people = []
    for item in raw["people"][:MAX_PEOPLE_PER_MESSAGE]:
        if not isinstance(item, dict):
            continue
        time_text, ask = _time(_text(item.get("time"), 12), item.get("time_certain") is True)
        person = Mentioned(
            name=_text(item.get("name"), MAX_NAME),
            relation=_text(item.get("relation"), MAX_RELATION),
            date_text=_date(_text(item.get("date"), 20), narrative),
            time_text=time_text,
            ask_ampm=ask,
            place_text=_text(item.get("place"), MAX_PLACE),
        )
        if person.name or person.date_text or person.place_text:
            people.append(person)
    if not people:
        return None
    return Extraction(
        tuple(people),
        _text(raw.get("question"), MAX_QUESTION),
        _text(raw.get("about"), MAX_NAME),
    )


async def extract_people(narrative: str, client=None) -> Extraction | None:
    """Ask the local model to read the message. None if the model is off, fails, or finds no one."""
    narrative = narrative[:MAX_NARRATIVE_CHARS]
    reply = await narrate.complete(
        EXTRACT_SYSTEM,
        f"Message:\n{narrative}",
        client,
        model=narrate.AI_MODEL,
        timeout=narrate.AI_TIMEOUT_SECONDS,
    )
    return parse_extraction(reply, narrative) if reply else None


def match_person(text: str, people) -> object | None:
    """The one saved person whose first name appears in `text` as a whole word; None if none or more than one.
    This is the offline fallback for "who is this about"; with the model on, the model decides.
    """
    words = set(re.findall(r"[^\W\d_]+", text.casefold()))
    hits = [p for p in people if p.name.split() and p.name.split()[0].casefold() in words]
    return hits[0] if len(hits) == 1 else None
