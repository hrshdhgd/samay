"""Grounded questions and answers.

A question is first sorted into a topic key (for example "planet:saturn"). The answer is then
built only from checked entries, quoted word for word, plus facts computed from the person's own
chart. Nothing is generated: a sorter, rules or a local model, only picks the topic, and a model's
choice is accepted only if it is one of the known keys. Questions outside the known topics (such as
predictions) get no answer, and the reply says why.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import narrate, service
from .engine import entries as entry_store
from .engine.entries import Entry
from .engine.ephemeris import GRAHAS
from .engine.vedic import DASHA_YEARS, RASHIS, SIGNS, house_from, sign_index
from .models import ResolvedBirth

# Calculation systems samay computes; entries tied to any other system are never used.
SYSTEMS = frozenset({"vimshottari"})

PLANET_NAMES = {
    "sun": ("sun", "surya", "suryan", "ravi"),
    "moon": ("moon", "chandra", "chandrama", "soma"),
    "mars": ("mars", "mangal", "mangala", "kuja", "angaraka"),
    "mercury": ("mercury", "budh", "budha"),
    "jupiter": ("jupiter", "guru", "brihaspati", "brihaspathi"),
    "venus": ("venus", "shukra", "sukra"),
    "saturn": ("saturn", "shani", "sani", "shanidev"),
    "rahu": ("rahu",),
    "ketu": ("ketu",),
}
_ALIAS = {alias: planet for planet, aliases in PLANET_NAMES.items() for alias in aliases}
DASHA_WORDS = ("dasha", "dasa", "mahadasha", "antardasha", "period", "chapter")
KALAPURUSHA_WORDS = ("kalapurusha", "kalapurush", "purusha")
TOPICS = frozenset(
    [f"planet:{p}" for p in GRAHAS] + [f"dasha:{p}" for p in GRAHAS] + ["dasha:current", "concept:kalapurusha"]
)
_WORD = re.compile(r"[a-z]+")

RAHU_KETU_FACT = (
    "Rahu and Ketu are not planets you can see. They are the two points where the Moon's path "
    "crosses the Sun's path in the sky."
)


@dataclass(frozen=True)
class Answer:
    topic: str | None  # None: the question is outside what samay can answer from sources
    entries: tuple[Entry, ...]
    facts: tuple[str, ...]  # computed from the person's own chart
    notes: tuple[str, ...] = ()  # general astronomical notes, not about this person
    name_line: str | None = None  # "Shani is the Sanskrit and Hindi name for Saturn." when asked by that name


def sort_question(text: str) -> str | None:
    """Rule-based sorter: a planet name (English or Sanskrit) and whether the question is about a
    dasha. Returns a key from TOPICS, or None."""
    words = _WORD.findall(text.casefold())
    if any(w in KALAPURUSHA_WORDS for w in words) or "cosmic person" in text.casefold():
        return "concept:kalapurusha"
    planets = [_ALIAS[w] for w in words if w in _ALIAS]
    about_dasha = any(w in DASHA_WORDS for w in words)
    if planets:
        return f"{'dasha' if about_dasha else 'planet'}:{planets[0]}"
    if about_dasha:
        return "dasha:current"
    return None


MODEL_SYSTEM = (
    "You sort questions about Vedic astrology into one topic key. Reply with exactly one key from "
    "the list and nothing else. Reply 'none' if no key fits, including any request for a "
    "prediction."
)


async def sort_with_model(text: str, client=None) -> str | None:
    """Local-model sorter for messier wording. Its reply is used only if it is a known key;
    otherwise, or if the model is off or fails, the rule-based sorter decides."""
    keys = "\n".join(sorted(TOPICS))
    reply = await narrate.complete(MODEL_SYSTEM, f"Keys:\n{keys}\nnone\n\nQuestion: {text}\nKey:", client)
    if reply:
        key = reply.strip().split()[0].strip("`'\".,").casefold() if reply.strip() else ""
        if key in TOPICS:
            return key
        if key == "none":
            return None
    return sort_question(text)


def name_used(question: str, planet: str) -> str | None:
    """The Sanskrit or Hindi name the person used for `planet`, if they did not use the English one."""
    words = _WORD.findall(question.casefold())
    if planet in words:
        return None
    for w in words:
        if _ALIAS.get(w) == planet and w != planet:
            return w
    return None


def _planet_facts(planet: str, birth: ResolvedBirth) -> list[str]:
    chart = service.natal_report(birth).chart
    p = chart.planets[planet]
    sign = sign_index(p.longitude)
    house = house_from(sign_index(chart.ascendant), sign)
    line = (
        f"In your birth chart, {planet.title()} is in {SIGNS[sign]} ({RASHIS[sign]}), "
        f"the {_ordinal(house)} house from your lagna (rising sign)"
    )
    if p.retrograde and planet not in ("rahu", "ketu"):
        line += ", and was moving backwards (retrograde)"
    return [line + "."]


def _dasha_facts(planet: str, birth: ResolvedBirth, now: datetime) -> list[str]:
    for period in service.natal_report(birth).dashas:
        if period.lord == planet:
            status = "you are in it now" if period.contains(now) else (
                "it is still ahead" if period.start > now else "it has ended")
            start = "your birth" if period.start < birth.utc else f"{period.start:%b %Y}"
            span = f"{start} – {period.end:%b %Y}"
            return [f"Your {planet.title()} chapter (dasha) lasts {DASHA_YEARS[planet]} years: {span}; {status}."]
    return [f"A {planet.title()} chapter (dasha) does not fall within your 120-year cycle."]


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def resolve_topic(topic: str | None, birth: ResolvedBirth | None, now: datetime) -> str | None:
    """'dasha:current' becomes the running chapter's planet when the birth is known."""
    if topic == "dasha:current" and birth is not None:
        running = service.today_report(birth, now).current_dasha
        if running:
            return f"dasha:{running[0].lord}"
    return topic


def answer_topic(
    topic: str | None,
    birth: ResolvedBirth | None,
    now: datetime,
    entries_dir: Path | None = None,
    question: str = "",
) -> Answer:
    """The answer for a sorted topic: checked entries for it, plus the person's own chart facts."""
    topic = resolve_topic(topic, birth, now)
    if topic is None or topic not in TOPICS:
        return Answer(None, (), ())
    found = entry_store.answers_for(topic, SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)
    kind, _, subject = topic.partition(":")
    facts: list[str] = []
    if birth is not None and subject in GRAHAS:
        facts = _planet_facts(subject, birth) if kind == "planet" else _dasha_facts(subject, birth, now)
    notes = (RAHU_KETU_FACT,) if subject in ("rahu", "ketu") else ()  # astronomy, always useful
    alias = name_used(question, subject) if subject in GRAHAS else None
    name_line = f"{alias.title()} is the Sanskrit and Hindi name for {subject.title()}." if alias else None
    return Answer(topic, tuple(found), tuple(facts), notes, name_line)
