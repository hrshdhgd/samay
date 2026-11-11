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
from .engine import house_effects
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
PERSONAL_WORDS = ("my", "mine", "me", "i", "am", "current", "running", "now", "own")
# Offline fallback only (the model reads the message when it is on): a few single words, no question patterns.
FUTURE_WORDS = ("future", "forecast", "horoscope", "destiny", "fortune")
KALAPURUSHA_WORDS = ("kalapurusha", "kalapurush", "purusha")
LAGNA_WORDS = ("lagna", "ascendant", "rising")
ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}
_HOUSE_NUMBER = re.compile(r"\b(?:(\d{1,2})(?:st|nd|rd|th)?\s+(?:house|bhava)|(?:house|bhava)\s+(\d{1,2}))\b")
# Life areas people ask about, and the house(s) Brihat Jataka I.15-16 (and Iyer's note) assign to each. A question about
# marriage is answered from what the text says the 7th house stands for, plus what sits in that house in the chart.
LIFE_AREAS = {
    "marriage": ((7,), "marriage and partnership"),
    "career": ((10,), "work and career"),
    "children": ((5,), "children"),
    "wealth": ((2, 11), "money and gains"),
    "home": ((4,), "home and family comforts"),
    "siblings": ((3,), "brothers and sisters"),
    "father": ((9,), "father and teachers"),
    "health": ((1, 6), "health"),
}
# Offline fallback only: single words, no question patterns (the model reads the message when it is on).
LIFE_WORDS = {
    "marriage": "marriage", "marry": "marriage", "married": "marriage", "wedding": "marriage", "spouse": "marriage",
    "wife": "marriage", "husband": "marriage", "career": "career", "job": "career", "profession": "career",
    "children": "children", "child": "children", "kids": "children", "son": "children", "daughter": "children",
    "money": "wealth", "wealth": "wealth", "finances": "wealth", "health": "health", "illness": "health",
}
TOPICS = frozenset(
    [f"life:{a}" for a in LIFE_AREAS] +
    [f"planet:{p}" for p in GRAHAS] + [f"dasha:{p}" for p in GRAHAS] + [f"house:{n}" for n in range(1, 13)]
    + ["dasha:current", "concept:kalapurusha", "concept:dasha", "future:overview"]
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
    reading: house_effects.Reading | None = None  # chapter XX on this planet in this person's house
    shares: dict | None = None  # how much of the good and bad effects the text says apply
    more_readings: tuple = ()  # (Reading, shares) for each planet in the asked-about house, for life areas


def sort_question(text: str) -> str | None:
    """Rule-based sorter: a planet name (English or Sanskrit) and whether the question is about a
    dasha. Returns a key from TOPICS, or None."""
    words = _WORD.findall(text.casefold())
    if any(w in KALAPURUSHA_WORDS for w in words) or "cosmic person" in text.casefold():
        return "concept:kalapurusha"
    planets = [_ALIAS[w] for w in words if w in _ALIAS]
    about_dasha = any(w in DASHA_WORDS for w in words)
    if not planets and any(w in FUTURE_WORDS for w in words):
        return "future:overview"
    area = next((LIFE_WORDS[w] for w in words if w in LIFE_WORDS), None)
    if area and not planets and not about_dasha:
        return f"life:{area}"
    house = _house_asked(text.casefold(), words)
    if house and not planets:
        return f"house:{house}"
    if planets:
        return f"{'dasha' if about_dasha else 'planet'}:{planets[0]}"
    if about_dasha:  # "my current dasha" is personal; "what is a dasha?" asks for the idea
        return "dasha:current" if any(w in PERSONAL_WORDS for w in words) else "concept:dasha"
    return None


TOPIC_HELP = {
    "planet:<planet>": "what a planet stands for: sun, moon, mars, mercury, jupiter, venus, saturn, rahu or ketu "
                       "(also by a Sanskrit name such as shani, guru or shukra)",
    "dasha:<planet>": "the dasha (life chapter) of that planet",
    "dasha:current": "the person's own current dasha",
    "concept:dasha": "what a dasha is, in general",
    "house:<1-12>": "what a house means; the lagna or ascendant is house:1",
    "concept:kalapurusha": "the cosmic person (Kalapurusha)",
    "life:<area>": "an area of the person's life: " + ", ".join(LIFE_AREAS) + " (a marriage question is life:marriage)",
    "future:overview": "the person's future, luck or what to expect: any horoscope-style question about their own life",
}
MODEL_SYSTEM = (
    "You route messages sent to a Jyotish chat bot. Reply with exactly one topic key and nothing else, or 'none' "
    "for greetings, thanks, small talk or anything that fits no topic. Pick a topic only if the message is really "
    "about it; a wrong topic is worse than 'none'. A short follow-up such as 'and Jupiter?' "
    "or 'what about the next one?' is about the same kind of topic as the previous one. Topics:\n"
    + "\n".join(f"- {key}: {what}" for key, what in TOPIC_HELP.items())
)


async def sort_with_model(text: str, client=None, previous: str | None = None) -> str | None:
    """Local-model router. It reads the message (and the previous topic, for follow-ups) and picks a known key or
    'none'. Its reply is used only if it is a known key; if the model is off or fails, a few plain rules decide."""
    keys = "\n".join(sorted(TOPICS))
    prompt = f"Keys:\n{keys}\nnone\n\nPrevious topic: {previous or 'none'}\n\nMessage: {text[:MAX_QUESTION_CHARS]}\nKey:"
    reply = await narrate.complete(MODEL_SYSTEM, prompt, client)
    if reply:
        key = reply.strip().split()[0].strip("`'\".,").casefold() if reply.strip() else ""
        if key in TOPICS:
            return key
        if key == "none":
            return None
    return sort_question(text)


def _house_asked(text: str, words: list[str]) -> int | None:
    """The house number a question is about: '4th house', 'house 4', 'fourth house', or the lagna."""
    m = _HOUSE_NUMBER.search(text)
    if m:
        n = int(m.group(1) or m.group(2))
        return n if 1 <= n <= 12 else None
    for i, w in enumerate(words[:-1]):
        if w in ORDINAL_WORDS and words[i + 1] in ("house", "bhava"):
            return ORDINAL_WORDS[w]
    if any(w in LAGNA_WORDS for w in words):
        return 1
    return None


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


def _transit_facts(report) -> list[str]:
    """Where the slow planets are now, counted from the person's birth Moon sign. Positions only."""
    out = []
    for planet, house in report.transit_houses:
        sign = sign_index(report.sky.planets[planet].longitude)
        out.append(f"{planet.title()} is in {SIGNS[sign]} ({RASHIS[sign]}), the {_ordinal(house)} sign from your Moon sign.")
    return out


def _future_answer(birth: ResolvedBirth | None, now: datetime, entries_dir: Path | None) -> Answer:
    """A reading of the period of life the person is in: the running dasha and what the checked text lists for it,
    where that planet sits in their chart (Brihat Jataka chapter 20), and where Jupiter and Saturn are now.
    It never says that a particular event will happen."""
    if birth is None:
        return Answer("future:overview", (), ())
    report = service.today_report(birth, now)
    facts = _transit_facts(report)
    if report.current_dasha is None:
        return Answer("future:overview", (), tuple(facts))
    maha, antar = report.current_dasha
    lord = maha.lord
    chart = service.natal_report(birth).chart
    entries = entry_store.answers_for(f"dasha:{lord}", SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)
    own = [*_dasha_facts(lord, birth, now),
           f"Inside it you are in the {antar.lord.title()} sub-chapter until {antar.end:%d %b %Y}.",
           *_planet_facts(lord, birth)]
    reading = house_effects.reading(chart, lord) if lord in house_effects.PLANETS else None
    shares = house_effects.shares(house_effects.load_rules(), reading) if reading and reading.effects else None
    return Answer("future:overview", tuple(entries), tuple(own + facts), (), None,
                  reading if shares else None, shares)


def _life_answer(area: str, birth: ResolvedBirth | None, entries_dir: Path | None) -> Answer:
    """A life area (marriage, career, ...) read through the house(s) the text assigns to it: what that house stands for,
    and, with a birth, which sign it is in and what planets sit there, each with its chapter 20 reading."""
    houses = LIFE_AREAS[area][0]
    folder = entries_dir or entry_store.ENTRIES_DIR
    found = [e for h in houses for e in entry_store.answers_for(f"house:{h}", SYSTEMS, folder)]
    facts: list[str] = []
    readings: list[tuple] = []
    if birth is not None:
        chart = service.natal_report(birth).chart
        lagna = sign_index(chart.ascendant)
        rules = house_effects.load_rules()
        for h in houses:
            sign = (lagna + h - 1) % 12
            tenants = [g for g in GRAHAS if sign_index(chart.planets[g].longitude) == sign]
            who = ", ".join(g.title() for g in tenants) if tenants else "no planets"
            facts.append(f"Your {_ordinal(h)} house is in {SIGNS[sign]} ({RASHIS[sign]}), with {who} in it.")
            for g in tenants:
                r = house_effects.reading(chart, g)
                if r is not None and r.effects:
                    readings.append((r, house_effects.shares(rules, r)))
    return Answer(f"life:{area}", tuple(found), tuple(facts), more_readings=tuple(readings))


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
    if topic == "future:overview":
        return _future_answer(birth, now, entries_dir)
    kind, _, subject = topic.partition(":")
    if kind == "life":
        return _life_answer(subject, birth, entries_dir)
    found = entry_store.answers_for(topic, SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)
    facts: list[str] = []
    if birth is not None and subject in GRAHAS:
        facts = _planet_facts(subject, birth) if kind == "planet" else _dasha_facts(subject, birth, now)
    if kind == "planet" and birth is not None and subject in GRAHAS:
        # What the house this planet sits in stands for, so "Saturn in your 4th house" is explained.
        chart = service.natal_report(birth).chart
        house = house_from(sign_index(chart.ascendant), sign_index(chart.planets[subject].longitude))
        found = [*found, *entry_store.answers_for(f"house:{house}", SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)]
    notes = (RAHU_KETU_FACT,) if subject in ("rahu", "ketu") else ()  # astronomy, always useful
    alias = name_used(question, subject) if subject in GRAHAS else None
    name_line = f"{alias.title()} is the Sanskrit and Hindi name for {subject.title()}." if alias else None
    reading = shares = None
    if kind == "planet" and birth is not None:
        reading = house_effects.reading(service.natal_report(birth).chart, subject)
        if reading is not None and reading.effects:
            shares = house_effects.shares(house_effects.load_rules(), reading)
        else:
            reading = None
    return Answer(topic, tuple(found), tuple(facts), notes, name_line, reading, shares)


AI_SYSTEM = (
    "You are samay, a warm, friendly guide to Vedic astrology (Jyotish) in a family chat, and you talk naturally. "
    "For greetings or small talk reply briefly and kindly, and mention that you can explain planets, houses and "
    "dashas and read the current period of life. "
    "Answer in plain English in at most 150 words, as plain text with no markdown. "
    "Be honest that Jyotish is a traditional belief system and not science. "
    "If asked about the future, give a warm, thoughtful reading of the themes and tendencies of the current "
    "period, using the facts supplied, the way a thoughtful astrologer would, and keep it hopeful and grounded. "
    "Never state that a specific event will or will not happen, never give dates for events, and do not give "
    "medical, legal or financial advice. "
    "Verified facts may be supplied; never contradict them. Everything else you say is your own general "
    "knowledge, so if you are unsure, say so."
)
MAX_QUESTION_CHARS = 500
MAX_AI_CHARS = 1200


def _ai_prompt(question: str, answer: Answer, history=()) -> str:
    verified = [e.english for e in answer.entries] + list(answer.facts) + list(answer.notes)
    if answer.reading is not None:
        r = answer.reading
        verified.append(f"Brihat Jataka, chapter 20, on {r.planet.title()} in house {r.house}: "
                        + "; ".join(e.text for e in r.effects))
    for r, _ in answer.more_readings:
        verified.append(f"Brihat Jataka, chapter 20, on {r.planet.title()} in house {r.house}: "
                        + "; ".join(e.text for e in r.effects))
    parts = []
    if verified:
        parts.append("Verified facts:\n" + "\n".join(f"- {f}" for f in verified))
    if history:
        parts.append("Recent conversation:\n" + "\n".join(f"Person: {q}\nYou: {r}" for q, r in history))
    parts.append(f"Question: {question[:MAX_QUESTION_CHARS]}")
    return "\n\n".join(parts)


async def ai_answer(question: str, answer: Answer, client=None, history=()) -> str | None:
    """The model's own answer to the question, shown apart from the sourced one and labelled as the AI's.
    It is given the checked entries and chart facts as verified context. None if the model is off or fails."""
    reply = await narrate.complete(
        AI_SYSTEM, _ai_prompt(question, answer, history), client,
        model=narrate.AI_MODEL, timeout=narrate.AI_TIMEOUT_SECONDS,
    )
    if not reply:
        return None
    if len(reply) > MAX_AI_CHARS:
        reply = reply[:MAX_AI_CHARS].rsplit(" ", 1)[0].rstrip() + "…"
    return reply
