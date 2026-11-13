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
from .engine import (
    antardasha,
    ashtakavarga,
    chandra_yogas,
    conjunctions,
    health,
    house_effects,
    house_strength,
    house_timing,
    longevity,
    lordship,
    moon_aspects,
    moon_nature,
    nabhasa,
    phaladeepika_yogas,
    planet_houses,
    raja_yogas,
    women,
)
from .engine import entries as entry_store
from .engine.entries import Entry
from .engine.ephemeris import GRAHAS
from .engine.vedic import DASHA_YEARS, RASHIS, SIGNS, house_from, sign_index
from .models import OutlookReport, ResolvedBirth
from .subject import SELF, Subject

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
# Offline fallback only: the period a question asks about ("my week", "this year", "the next few years").
SPAN_WORDS = {"week": "week", "weekend": "week", "fortnight": "fortnight", "month": "month", "year": "year",
              "years": "years", "decade": "years"}
OUTLOOK_TOPICS = tuple(f"future:{span}" for span in service.OUTLOOK_SPANS)
WHEN_PREFIX = "when:"
ASHTAKA_WORDS = ("ashtakavarga", "ashtakvarga", "sarvashtakavarga", "bindu", "bindus")
CONJUNCTION_WORDS = ("conjunction", "conjunctions", "together")
YOGA_WORDS = ("yoga", "yogas", "combination", "combinations")
WOMEN_WORDS = ("woman", "women", "female", "feminine")
STRENGTH_WORDS = ("strong", "weak", "strength", "houses")
LONGEVITY_WORDS = ("longevity", "lifespan", "die", "death", "dying", "longlived")
HEALTH_WORDS = ("disease", "diseases", "ailment", "ailments", "sickness", "sick")
MOON_WORDS = ("nakshatra", "nakshatras", "rashi", "personality", "character", "temperament")
# Topics computed from the chart rather than answered from entries: no entry is expected, so no miss is recorded.
COMPUTED_PREFIXES = ("future:", "chart:")
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
    "home": ((4,), "home, property and vehicles"),
    "siblings": ((3,), "brothers and sisters"),
    "father": ((9,), "father and teachers"),
    "health": ((1, 6), "health"),
    "education": ((4, 5), "education and intelligence"),
    "travel": ((12,), "travel"),
    "enemies": ((6,), "enemies and disputes"),
    "dharma": ((5, 9), "merit and past karma"),
    "mother": ((4,), "mother"),
    "family": ((2,), "family and speech"),
}
# Offline fallback only: single words, no question patterns (the model reads the message when it is on).
LIFE_WORDS = {
    "marriage": "marriage", "marry": "marriage", "married": "marriage", "wedding": "marriage", "spouse": "marriage",
    "wife": "marriage", "husband": "marriage", "career": "career", "job": "career", "profession": "career",
    "children": "children", "child": "children", "kids": "children", "son": "children", "daughter": "children",
    "money": "wealth", "wealth": "wealth", "finances": "wealth", "health": "health", "illness": "health",
    "property": "home", "vehicle": "home", "car": "home", "education": "education", "study": "education",
    "studies": "education", "exam": "education", "abroad": "travel", "travel": "travel", "enemies": "enemies",
    "enemy": "enemies", "court": "enemies", "mother": "mother", "family": "family", "karma": "dharma",
}
TOPICS = frozenset(
    [f"life:{a}" for a in LIFE_AREAS] +
    [f"planet:{p}" for p in GRAHAS] + [f"dasha:{p}" for p in GRAHAS] + [f"house:{n}" for n in range(1, 13)]
    + [f"when:{a}" for a in LIFE_AREAS]
    + ["dasha:current", "concept:kalapurusha", "concept:dasha", "future:overview", *OUTLOOK_TOPICS, "chart:ashtakavarga",
    "chart:moon", "chart:conjunctions", "chart:yogas", "chart:health", "chart:longevity", "chart:houses", "chart:women"]
)
_WORD = re.compile(r"[a-z]+")

RAHU_KETU_FACT = (
    "Rahu and Ketu are not planets you can see. They are the two points where the Moon's path "
    "crosses the Sun's path in the sky."
)


@dataclass(frozen=True)
class SecondVoice:
    """Phaladeepika chapter 8 on one planet in one house of this chart (a second text beside Brihat Jataka XX)."""
    planet: str
    house: int
    rows: tuple[planet_houses.Row, ...]
    verse: str  # the text's verse range for the planet, e.g. "1-4"


@dataclass(frozen=True)
class YogasView:
    """The person's yogas from three sources, each shown only once its own rules file has been checked."""
    nabhasa: nabhasa.Nabhasa
    chapter6: tuple
    chapter6_checked: bool
    blemish_note: str
    raja: tuple
    raja_checked: bool
    raja_family: str


@dataclass(frozen=True)
class MoonView:
    """The person's Moon sign and nakshatra with Brihat Jataka XVII and XVI on them."""
    sign: int
    sign_text: moon_nature.Description
    nakshatra: moon_nature.Description
    pada: int
    nakshatra_index: int
    checked: bool  # the descriptions are shown only once a person has checked the file
    conditions: dict
    edition: str
    pages: str
    yogas: tuple = ()  # chandra_yogas.Found, Brihat Jataka XIII, once its rules are checked
    yogas_checked: bool = False
    yoga_edition: str = ""
    yoga_pages: str = ""
    aspects: moon_aspects.MoonAspects | None = None  # Brihat Jataka XIX, once its rules are checked
    aspects_checked: bool = False
    aspect_texts: tuple = ()  # (aspect rule, degree rule, rising-sign note)


@dataclass(frozen=True)
class AshtakaView:
    """The person's ashtakavarga: points per sign (Aries first), per planet and added up."""
    sarva: tuple[int, ...]
    bhinna: dict
    lagna: int
    checked: bool  # the numbers are shown only once a person has checked the tables
    threshold: int
    above: str
    below: str
    verse: str
    edition: str
    pages: str
    variants: int


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
    who: Subject = SELF  # whose chart this answer is about
    outlook: OutlookReport | None = None  # the transits over a period ahead (future:week ... future:years)
    second: tuple[SecondVoice, ...] = ()  # Phaladeepika 8, once its rules are checked
    ashtaka: AshtakaView | None = None  # chart:ashtakavarga
    moon: MoonView | None = None  # chart:moon
    together: tuple[conjunctions.Together, ...] | None = None  # chart:conjunctions
    together_checked: bool = False
    yogas: YogasView | None = None  # chart:yogas
    timing: house_timing.Timing | None = None  # when:<area>
    timing_checked: bool = False
    health: health.Health | None = None  # chart:health
    health_checked: bool = False
    longevity: longevity.Longevity | None = None  # chart:longevity
    longevity_checked: bool = False
    houses: tuple | None = None  # chart:houses
    houses_checked: bool = False
    women: tuple | None = None  # chart:women
    women_checked: bool = False
    lordship: tuple[lordship.Verdict, ...] = ()  # Phaladeepika 20: the dasha through the houses its lord rules


_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_BIRTH_DATE = re.compile(
    rf"\b\d{{1,2}}[-/.]\d{{1,2}}[-/.]\d{{4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTHS},?\s+\d{{4}}\b"
    rf"|\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.IGNORECASE)
_BIRTH_WORDS = re.compile(r"\b(?:born|birth|birthday|dob)\b", re.IGNORECASE)


def describes_birth(text: str) -> bool:
    """A plain rule for when the model cannot help: the message gives a full date and says 'born' or 'birth'."""
    return bool(_BIRTH_DATE.search(text) and _BIRTH_WORDS.search(text))


def sort_question(text: str) -> str | None:
    """Rule-based sorter: a planet name (English or Sanskrit) and whether the question is about a
    dasha. Returns a key from TOPICS, or None."""
    words = _WORD.findall(text.casefold())
    if any(w in KALAPURUSHA_WORDS for w in words) or "cosmic person" in text.casefold():
        return "concept:kalapurusha"
    planets = [_ALIAS[w] for w in words if w in _ALIAS]
    about_dasha = any(w in DASHA_WORDS for w in words)
    if any(w in ASHTAKA_WORDS for w in words):
        return "chart:ashtakavarga"
    if not planets and any(w in CONJUNCTION_WORDS for w in words) and any(w in PERSONAL_WORDS for w in words):
        return "chart:conjunctions"
    if not planets and any(w in YOGA_WORDS for w in words) and any(w in PERSONAL_WORDS for w in words):
        return "chart:yogas"
    if not planets and any(w in WOMEN_WORDS for w in words) and {"horoscope", "chart", "husband"} & set(words):
        return "chart:women"
    if not planets and {"strength", "houses"} & set(words) and any(w in PERSONAL_WORDS for w in words):
        return "chart:houses"
    if not planets and (any(w in LONGEVITY_WORDS for w in words) or {"long", "live"} <= set(words)) and any(w in PERSONAL_WORDS for w in words):
        return "chart:longevity"
    if not planets and any(w in HEALTH_WORDS for w in words) and any(w in PERSONAL_WORDS for w in words):
        return "chart:health"
    if not planets and any(w in MOON_WORDS for w in words) and any(w in PERSONAL_WORDS for w in words):
        return "chart:moon"  # "what is my nakshatra", not "what is a nakshatra"
    area = next((LIFE_WORDS[w] for w in words if w in LIFE_WORDS), None)
    span = next((SPAN_WORDS[w] for w in words if w in SPAN_WORDS), None)
    if area and "when" in words and not planets and not about_dasha:
        return f"when:{area}"
    if span and not planets and not area and not about_dasha:
        return f"future:{span}"
    if not planets and any(w in FUTURE_WORDS for w in words):
        return "future:overview"
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
    "people:add": "the message gives someone's birth details (a date, time or place of birth), or asks to add a person",
    "chart:moon": "the person's nature, character or personality, from the sign and the nakshatra their Moon is in",
    "when:<area>": "WHEN something may happen in an area of the person's life (when:marriage for 'when will I get married', also career, children, wealth, home, health, travel...): the book's timing conditions over the next years",
    "chart:women": "the old book's pointers about a woman's husband, marriage and children (a sensitive topic: the bot asks first)",
    "chart:houses": "which houses of the chart are helped or harmed, and why (the strength of each house)",
    "chart:longevity": "how long a life the chart points to, dangers to life at birth and the cause of death (a sensitive topic: the bot asks first)",
    "chart:health": "which diseases or troubles the chart points to, by the planets in the 6th, 8th and 12th houses and the lord of the 6th (an old text's list, not medical advice)",
    "chart:yogas": "the person's yogas: the named planetary combinations in their chart (Nabhasa, raja, Mahapurusha, Lakshmi and the rest)",
    "chart:conjunctions": "which planets sit together in one sign in the person's chart and what the texts say of each pair (yogas, planetary combinations)",
    "chart:ashtakavarga": "the person's ashtakavarga: how many benefic points each sign has in their chart and which signs are strong",
    "future:overview": "the person's future, luck or what to expect in general, with no particular period named",
    "future:week": "the coming week or the next few days (what the week looks like, this weekend)",
    "future:fortnight": "the next two weeks",
    "future:month": "the coming month or the next few weeks",
    "future:year": "the coming year, this year or the next twelve months",
    "future:years": "the next few years, the long term, or the coming decade",
}
MODEL_SYSTEM = (
    "You route messages sent to a Jyotish chat bot. Reply with exactly one topic key and nothing else, or 'none' "
    "for greetings, thanks, small talk or anything that fits no topic. You may add ' | ' and whom the message is "
    "about: the exact name of one of the listed People, or 'me' for the person writing; leave that part out when "
    "it is about the same person as before. A message about a child, spouse or parent whose name is not in the "
    "list is people:add only if it gives their birth details. Pick a topic only if the message is really "
    "about it; a wrong topic is worse than 'none'. A short follow-up such as 'and Jupiter?' "
    "or 'what about the next one?' is about the same kind of topic as the previous one. Topics:\n"
    + "\n".join(f"- {key}: {what}" for key, what in TOPIC_HELP.items())
)


@dataclass(frozen=True)
class Route:
    topic: str | None  # a key from TOPICS, or None
    person: str | None = None  # a person's name, "me", or None when the message is about whoever it was about before
    add: bool = False  # the message describes someone to add


def _parse_route(reply: str | None, names: set[str]) -> Route | None:
    """The model's reply as a Route, accepting only known topic keys and listed names; None if it is not usable."""
    if not reply or not reply.strip():
        return None
    left, _, right = reply.strip().splitlines()[0].partition("|")
    key = left.strip().split()[0].strip("`'\".,").casefold() if left.strip() else ""
    name = right.strip().strip("`'\".,")
    person = None
    if name:
        person = "me" if name.casefold() == "me" else next((n for n in names if n.casefold() == name.casefold()), None)
    if key == "people:add":
        return Route(None, None, True)
    if key in TOPICS:
        return Route(key, person)
    if key == "none":
        return Route(None)
    return None


async def route_with_model(text: str, client=None, previous: str | None = None, people=(), active: str | None = None) -> Route:
    """Local-model router. It reads the message with the people the user has told us about, the person we are talking
    about now and the previous topic, so follow-ups and "and Arjun?" work. Its reply is used only if it is a known
    topic key and a listed name; if the model is off or fails, a few plain single-word rules decide the topic."""
    keys = "\n".join(sorted(TOPICS))
    roster = "; ".join(["me (the person writing)", *(f"{n} ({r})" if r else n for n, r in people)])
    prompt = (f"Keys:\n{keys}\nnone\n\nPeople: {roster}\nCurrently talking about: {active or 'me'}\n"
              f"Previous topic: {previous or 'none'}\n\nMessage: {text[:MAX_QUESTION_CHARS]}\nAnswer:")
    names = {n for n, _ in people}
    reply = await narrate.complete(MODEL_SYSTEM, prompt, client)
    route = _parse_route(reply, names)
    if route is None and reply and narrate.AI_MODEL != narrate.OLLAMA_MODEL:
        # The small model answered but not usably: ask the larger one once. A silent reply (timeout, model down) is
        # not retried: the larger model is slower, and the whole bot waits for this call.
        route = _parse_route(await narrate.complete(MODEL_SYSTEM, prompt, client, model=narrate.AI_MODEL), names)
    return route if route is not None else rule_route(text)


def rule_route(text: str) -> Route:
    """The plain-rule route, used when the model is off, silent or unusable."""
    if describes_birth(text):
        return Route(None, None, True)
    return Route(sort_question(text))


async def sort_with_model(text: str, client=None, previous: str | None = None) -> str | None:
    """The topic only (see route_with_model); kept for callers that do not deal with people."""
    return (await route_with_model(text, client, previous)).topic


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


def _planet_facts(planet: str, birth: ResolvedBirth, who: Subject = SELF) -> list[str]:
    chart = service.natal_report(birth).chart
    p = chart.planets[planet]
    sign = sign_index(p.longitude)
    house = house_from(sign_index(chart.ascendant), sign)
    line = (
        f"In {who.your} birth chart, {planet.title()} is in {SIGNS[sign]} ({RASHIS[sign]}), "
        f"the {_ordinal(house)} house from {who.your} lagna (rising sign)"
    )
    if p.retrograde and planet not in ("rahu", "ketu"):
        line += ", and was moving backwards (retrograde)"
    return [line + "."]


def _dasha_facts(planet: str, birth: ResolvedBirth, now: datetime, who: Subject = SELF) -> list[str]:
    for period in service.natal_report(birth).dashas:
        if period.lord == planet:
            status = f"{who.you_are} in it now" if period.contains(now) else (
                "it is still ahead" if period.start > now else "it has ended")
            start = f"{who.your} birth" if period.start < birth.utc else f"{period.start:%b %Y}"
            span = f"{start} – {period.end:%b %Y}"
            return [f"{who.Your} {planet.title()} chapter (dasha) lasts {DASHA_YEARS[planet]} years: {span}; {status}."]
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


def _transit_facts(report, who: Subject = SELF) -> list[str]:
    """Where the slow planets are now, counted from the person's birth Moon sign. Positions only."""
    out = []
    for planet, house in report.transit_houses:
        sign = sign_index(report.sky.planets[planet].longitude)
        out.append(f"{planet.title()} is in {SIGNS[sign]} ({RASHIS[sign]}), the {_ordinal(house)} sign from {who.your} Moon sign.")
    return out


def _yogas_view(birth: ResolvedBirth | None) -> YogasView | None:
    if birth is None:
        return None
    chart = service.natal_report(birth).chart
    nab, pd6, raja = nabhasa.load_rules(), phaladeepika_yogas.load_rules(), raja_yogas.load_rules()
    return YogasView(nabhasa.find(nab, chart), phaladeepika_yogas.find(pd6, chart), pd6.servable, pd6.blemish_note,
                     raja_yogas.find(raja, chart), raja.servable, raja.family["verse"] + ": " + raja.family["anyone"])


def _moon_view(birth: ResolvedBirth | None) -> MoonView | None:
    if birth is None:
        return None
    rules = moon_nature.load_rules()
    chart = service.natal_report(birth).chart
    sign, sign_text, nak, nak_text, pada = moon_nature.for_moon(rules, chart.planets["moon"].longitude)
    yoga_rules = chandra_yogas.load_rules()
    yogas = chandra_yogas.find(yoga_rules, chart)
    asp_rules = moon_aspects.load_rules()
    return MoonView(sign, sign_text, nak_text, pada, nak, rules.servable, rules.conditions, rules.edition, rules.pages,
                    yogas.found, yogas.checked, yoga_rules.edition, yoga_rules.pages,
                    moon_aspects.find(asp_rules, chart), asp_rules.servable,
                    (asp_rules.aspect_text, asp_rules.degree_text, asp_rules.degree_rising))


SENSITIVE_TOPICS = frozenset({"chart:longevity", "chart:women"})
CHILD_SENSITIVE_TOPICS = SENSITIVE_TOPICS | {"chart:health"}


def sensitivity(topic: str | None, subject: Subject) -> str | None:
    """"sensitive" when the bot must show a warning and wait for a tap before answering, "child" for the stronger warning about a person
    under 18, None when the answer can be given straight away."""
    if topic is None:
        return None
    if subject.minor and topic in CHILD_SENSITIVE_TOPICS:
        return "child"
    return "sensitive" if topic in SENSITIVE_TOPICS else None


def _ashtaka_view(birth: ResolvedBirth | None) -> AshtakaView | None:
    if birth is None:
        return None
    rules = ashtakavarga.load_rules()
    points = ashtakavarga.bhinna(rules, ashtakavarga.positions(service.natal_report(birth).chart))
    where = ashtakavarga.positions(service.natal_report(birth).chart)
    return AshtakaView(tuple(ashtakavarga.sarva(points)), points, where["lagna"], rules.servable, rules.threshold,
                       rules.above, rules.below, rules.sarva_verse, rules.edition, rules.pages,
                       sum(1 for v in rules.variants if "phaladeepika" in v))


def _lordship(birth: ResolvedBirth, *planets: str) -> tuple[lordship.Verdict, ...]:
    rules = lordship.load_rules()
    report = service.natal_report(birth)
    first = report.dashas[0].lord  # the dasha the person is born in counts as the first
    found = (lordship.judge(rules, report.chart, p, first) for p in dict.fromkeys(planets))
    return tuple(v for v in found if v is not None)


def _second_voice(chart, planet: str) -> SecondVoice | None:
    """What Phaladeepika chapter 8 says for this planet in the house it holds in the chart, once checked."""
    lagna = sign_index(chart.ascendant)
    house = house_from(lagna, sign_index(chart.planets[planet].longitude))
    found = planet_houses.load_rules().lookup(planet, house, lagna)
    return SecondVoice(planet, house, *found) if found else None


def _antardasha_fact(maha: str, antar: str) -> list[str]:
    """What Phaladeepika 21 says for this sub-chapter, once its rules file has been checked."""
    found = antardasha.load_rules().result(maha, antar)
    if found is None:
        return []
    text, verse = found
    return [f"For the {antar.title()} sub-chapter of the {maha.title()} chapter the text says: {text} (Phaladeepika 21.{verse})."]


def _future_answer(
    birth: ResolvedBirth | None, now: datetime, entries_dir: Path | None, subject: Subject = SELF
) -> Answer:
    """A reading of the period of life the person is in: the running dasha and what the checked text lists for it,
    where that planet sits in their chart (Brihat Jataka chapter 20), and where Jupiter and Saturn are now.
    It never says that a particular event will happen."""
    if birth is None:
        return Answer("future:overview", (), (), who=subject)
    report = service.today_report(birth, now)
    facts = _transit_facts(report, subject)
    if report.current_dasha is None:
        return Answer("future:overview", (), tuple(facts), who=subject)
    maha, antar = report.current_dasha
    lord = maha.lord
    chart = service.natal_report(birth).chart
    entries = entry_store.answers_for(f"dasha:{lord}", SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)
    own = [*_dasha_facts(lord, birth, now, subject),
           f"Inside it {subject.you_are} in the {antar.lord.title()} sub-chapter until {antar.end:%d %b %Y}.",
           *_antardasha_fact(lord, antar.lord),
           *_planet_facts(lord, birth, subject)]
    reading = house_effects.reading(chart, lord) if lord in house_effects.PLANETS else None
    shares = house_effects.shares(house_effects.load_rules(), reading) if reading and reading.effects else None
    return Answer("future:overview", tuple(entries), tuple(own + facts), (), None,
                  reading if shares else None, shares, who=subject, lordship=_lordship(birth, lord, antar.lord))


def _life_answer(area: str, birth: ResolvedBirth | None, entries_dir: Path | None, subject: Subject = SELF) -> Answer:
    """A life area (marriage, career, ...) read through the house(s) the text assigns to it: what that house stands for,
    and, with a birth, which sign it is in and what planets sit there, each with its chapter 20 reading."""
    houses = LIFE_AREAS[area][0]
    folder = entries_dir or entry_store.ENTRIES_DIR
    found = [e for h in houses for e in entry_store.answers_for(f"house:{h}", SYSTEMS, folder)]
    facts: list[str] = []
    readings: list[tuple] = []
    second: list[SecondVoice] = []
    if birth is not None:
        chart = service.natal_report(birth).chart
        lagna = sign_index(chart.ascendant)
        rules = house_effects.load_rules()
        for h in houses:
            sign = (lagna + h - 1) % 12
            tenants = [g for g in GRAHAS if sign_index(chart.planets[g].longitude) == sign]
            inside = ", ".join(g.title() for g in tenants) if tenants else "no planets"
            facts.append(f"{subject.Your} {_ordinal(h)} house is in {SIGNS[sign]} ({RASHIS[sign]}), with {inside} in it.")
            for g in tenants:
                r = house_effects.reading(chart, g)
                if r is not None and r.effects:
                    readings.append((r, house_effects.shares(rules, r)))
                if (voice := _second_voice(chart, g)) is not None:
                    second.append(voice)
    return Answer(f"life:{area}", tuple(found), tuple(facts), more_readings=tuple(readings), who=subject,
                  second=tuple(second))


def answer_topic(
    topic: str | None,
    birth: ResolvedBirth | None,
    now: datetime,
    entries_dir: Path | None = None,
    question: str = "",
    subject: Subject = SELF,
    tz: str | None = None,
) -> Answer:
    """The answer for a sorted topic: checked entries for it, plus the person's own chart facts."""
    topic = resolve_topic(topic, birth, now)
    if topic is None or topic not in TOPICS:
        return Answer(None, (), ())
    if topic == "future:overview":
        return _future_answer(birth, now, entries_dir, subject)
    if topic.startswith(WHEN_PREFIX):
        area = topic[len(WHEN_PREFIX):]
        report = service.timing_report(birth, now, area, tz) if birth is not None else None
        return Answer(topic, (), (), timing=report, timing_checked=house_timing.load_rules().servable, who=subject)
    if topic == "chart:women":
        wr = women.load_rules()
        found = women.find(wr, service.natal_report(birth).chart) if birth is not None else None
        return Answer(topic, (), (), women=found, women_checked=wr.servable, who=subject)
    if topic == "chart:houses":
        hs = house_strength.load_rules()
        found = house_strength.find(hs, service.natal_report(birth).chart) if birth is not None else None
        return Answer(topic, (), (), houses=found, houses_checked=hs.servable, who=subject)
    if topic == "chart:longevity":
        lrules = longevity.load_rules()
        found = longevity.find(lrules, service.natal_report(birth).chart) if birth is not None else None
        return Answer(topic, (), (), longevity=found, longevity_checked=lrules.servable, who=subject)
    if topic == "chart:health":
        hrules = health.load_rules()
        found = health.find(hrules, service.natal_report(birth).chart) if birth is not None else None
        return Answer(topic, (), (), health=found, health_checked=hrules.servable, who=subject)
    if topic == "chart:yogas":
        return Answer(topic, (), (), yogas=_yogas_view(birth), who=subject)
    if topic == "chart:conjunctions":
        rules = conjunctions.load_rules()
        found = conjunctions.find(rules, service.natal_report(birth).chart) if birth is not None else None
        return Answer(topic, (), (), together=found, together_checked=rules.servable, who=subject)
    if topic == "chart:moon":
        return Answer(topic, (), (), moon=_moon_view(birth), who=subject)
    if topic == "chart:ashtakavarga":
        return Answer(topic, (), (), ashtaka=_ashtaka_view(birth), who=subject)
    if topic in OUTLOOK_TOPICS:
        report = service.outlook_report(birth, now, topic.split(":")[1], tz) if birth is not None else None
        return Answer(topic, (), (), outlook=report, who=subject)
    kind, _, subject_key = topic.partition(":")
    if kind == "life":
        return _life_answer(subject_key, birth, entries_dir, subject)
    found = entry_store.answers_for(topic, SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)
    facts: list[str] = []
    if birth is not None and subject_key in GRAHAS:
        facts = (_planet_facts(subject_key, birth, subject) if kind == "planet"
                 else _dasha_facts(subject_key, birth, now, subject))
    if kind == "planet" and birth is not None and subject_key in GRAHAS:
        # What the house this planet sits in stands for, so "Saturn in the 4th house" is explained.
        chart = service.natal_report(birth).chart
        house = house_from(sign_index(chart.ascendant), sign_index(chart.planets[subject_key].longitude))
        found = [*found, *entry_store.answers_for(f"house:{house}", SYSTEMS, entries_dir or entry_store.ENTRIES_DIR)]
    notes = (RAHU_KETU_FACT,) if subject_key in ("rahu", "ketu") else ()  # astronomy, always useful
    alias = name_used(question, subject_key) if subject_key in GRAHAS else None
    name_line = f"{alias.title()} is the Sanskrit and Hindi name for {subject_key.title()}." if alias else None
    reading = shares = None
    if kind == "planet" and birth is not None:
        reading = house_effects.reading(service.natal_report(birth).chart, subject_key)
        if reading is not None and reading.effects:
            shares = house_effects.shares(house_effects.load_rules(), reading)
        else:
            reading = None
    voice = _second_voice(service.natal_report(birth).chart, subject_key) if kind == "planet" and birth is not None else None
    houses = _lordship(birth, subject_key) if kind == "dasha" and birth is not None else ()
    return Answer(topic, tuple(found), tuple(facts), notes, name_line, reading, shares, who=subject,
                  second=(voice,) if voice else (), lordship=houses)


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
    "The facts may be about someone other than the writer, such as their child: refer to that person by name. "
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
    verified += [f"Phaladeepika, chapter 8, on {v.planet.title()} in house {v.house}: " + "; ".join(r.text for r in v.rows)
                 for v in answer.second]
    if answer.outlook is not None:
        verified += outlook_facts(answer.outlook, answer.who)
    if answer.ashtaka is not None and answer.ashtaka.checked:
        verified += ashtaka_facts(answer.ashtaka, answer.who)
    verified += [lordship_fact(v) for v in answer.lordship]
    verified += conjunction_facts(answer.together or (), answer.who)
    if answer.timing is not None:
        verified += timing_facts(answer.timing, answer.who)
    if answer.health is not None:
        verified += health_facts(answer.health, answer.who)
    if answer.houses:
        verified += house_facts(answer.houses, answer.who)
    if answer.women:
        verified += [f"Phaladeepika {p.verse} ({p.detail}): {p.text}." for p in answer.women]
    if answer.yogas is not None:
        verified += yoga_facts(answer.yogas, answer.who)
    if answer.moon is not None and answer.moon.aspects is not None:
        verified += moon_aspect_facts(answer.moon, answer.who)
    if answer.moon is not None and (answer.moon.checked or answer.moon.yogas_checked):
        verified += moon_facts(answer.moon, answer.who)
    parts = []
    if not answer.who.is_self:
        relation = f", the writer's {answer.who.relation}" if answer.who.relation else ""
        parts.append(f"The question is about {answer.who.name}{relation}.")
        if answer.who.minor:
            parts.append("They are a child. Keep the reading gentle and about learning, character and growth; do not "
                         "mention marriage, wealth or career as expectations.")
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
        model=narrate.AI_MODEL, timeout=narrate.AI_TIMEOUT_SECONDS, max_tokens=narrate.AI_MAX_TOKENS,
    )
    if not reply:
        return None
    if len(reply) > MAX_AI_CHARS:
        reply = reply[:MAX_AI_CHARS].rsplit(" ", 1)[0].rstrip() + "…"
    return reply


def outlook_facts(report: OutlookReport, who: Subject = SELF) -> list[str]:
    """The period's transits as plain sentences for the AI (the bot shows its own layout of the same facts)."""
    out = [(f"The period is {report.start:%d %b %Y} to {report.end:%d %b %Y}. Transits are counted from "
            f"{who.your} Moon sign, {SIGNS[report.moon_sign]}, as Phaladeepika chapter 26 teaches.")]
    if report.dasha_at_start:
        maha, antar = report.dasha_at_start
        out.append(f"Running at the start: the {maha.lord.title()} chapter (mahadasha), {antar.lord.title()} "
                   f"sub-chapter until {antar.end:%d %b %Y}.")
    out += [f"From {a.start:%d %b %Y}: the {a.lord.title()} sub-chapter of the {lord.title()} chapter."
            for lord, a in report.dasha_changes]
    out += [f"Phaladeepika 21.{verse} on the {a.title()} sub-chapter of the {m.title()} chapter: {text}."
            for m, a, text, verse in report.antardasha]
    for s in report.stays:
        when = ("all through the period" if s.start is None and s.end is None
                else f"until {s.end:%d %b %Y}" if s.start is None
                else f"from {s.start:%d %b %Y}" if s.end is None
                else f"{s.start:%d %b %Y} to {s.end:%d %b %Y}")
        line = f"{s.planet.title()} in the {_ordinal(s.house)} house from the Moon sign, {when}"
        if s.effect:
            line += f": the text gives {s.effect} ({'a good house' if s.favourable else 'a hard house'} for it)"
            if s.blocked_by:
                line += f", but {', '.join(g.title() for g in s.blocked_by)} obstruct it (vedha)"
        out.append(line + ".")
    return out


def ashtaka_facts(view: AshtakaView, who: Subject = SELF) -> list[str]:
    """The sign totals as sentences for the AI."""
    by_house = [(h, SIGNS[(view.lagna + h - 1) % 12], view.sarva[(view.lagna + h - 1) % 12]) for h in range(1, 13)]
    line = "; ".join(f"{_ordinal(h)} house {sign}: {n}" for h, sign, n in by_house)
    head = (f"{who.Your} ashtakavarga points per house (Phaladeepika {view.verse}; more than {view.threshold} is "
            f"{view.above}; fewer: {view.below})")
    return [f"{head}: {line}."]


def moon_facts(view: MoonView, who: Subject = SELF) -> list[str]:
    """The Moon's sign and nakshatra descriptions as sentences for the AI."""
    return [f"Brihat Jataka XIII, {f.name}" + (f" ({f.detail})" if f.detail else "") + f": {f.text}" for f in view.yogas] + [
            f"Brihat Jataka XVII on {who.your} Moon in {SIGNS[view.sign]}: a person born with it {view.sign_text.text}",
            f"Brihat Jataka XVI on {who.your} Moon in {view.nakshatra.name}: a person born with it {view.nakshatra.text}",
            f"Brihat Jataka says: {view.conditions['sign'][1]}"]


def lordship_fact(v: lordship.Verdict) -> str:
    """One planet's lordship reading as a sentence for the AI."""
    return (f"Phaladeepika 20, the dasha of {v.planet.title()}, which rules the " + " and ".join(_ordinal(h) for h in v.owned)
            + f" house and stands in the {_ordinal(v.house)}: " + "; ".join(
                f"for the {_ordinal(h)} house, {'when strong' if k == 'strong' else 'when weak' if k == 'weak' else k}: {t}"
                for h, k, _, t in v.rows) + "." + "".join(f" Parasara's view (20.41): {t}." for _, t in v.nature)
            + "".join(f" Troublesome (20.24): {t}." for _, t in v.troublesome))


def conjunction_facts(together, who: Subject = SELF) -> list[str]:
    """The planets sharing a sign, with the texts for each pair, as sentences for the AI."""
    out = []
    for t in together:
        for (a, b), p in t.pairs:
            out.append(f"{who.Your} {a.title()} and {b.title()} are together in {SIGNS[t.sign]}. Brihat Jataka {p.verse_bj}: "
                       f"the person will be {p.bj}. Phaladeepika {p.verse_pd}: {p.pd}.")
    return out


def yoga_facts(view: YogasView, who: Subject = SELF) -> list[str]:
    """The yogas found, as sentences for the AI."""
    out = [f"Brihat Jataka 12 ({y.name} yoga; {y.detail}): a person born under it {y.text}" for y in view.nabhasa.yogas]
    out += [f"Phaladeepika {f.verse}, {f.name} ({f.detail}): {f.text}." for f in view.chapter6]
    out += [f"Brihat Jataka {f.verse} raja yoga ({f.detail}): {f.text}" for f in view.raja]
    return out


def moon_aspect_facts(view: MoonView, who: Subject = SELF) -> list[str]:
    """The planets aspecting the Moon, with what the text says for her sign and navamsa, as sentences for the AI."""
    a = view.aspects
    out = [f"Brihat Jataka XIX: {who.Your} Moon in {a.sign}, aspected by {p.title()}: the person will {t}." for p, t in a.in_sign]
    out += [f"Brihat Jataka XIX: {who.Your} Moon in the navamsa of {a.navamsa_lord.title()}, aspected by {p.title()}: the person will {t}."
            for p, t in a.in_navamsa]
    return out


def timing_facts(t, who: Subject = SELF) -> list[str]:
    """The timing windows as sentences for the AI. The book names conditions, never dates."""
    out = [f"Phaladeepika's timing rules for {t.area} from {t.start:%d %b %Y} to {t.end:%d %b %Y}. They are conditions, not dates."]
    for r in (*t.marriage, *t.general):
        if r.note:
            continue
        spans = "; ".join(f"{a:%d %b %Y} to {b:%d %b %Y}" for a, b in r.windows[:6]) or "no stretch in this period"
        out.append(f"Phaladeepika {r.verse} (from the {r.ref}, house {r.house}): {r.text}. Holds on {r.days} of {r.total} days: {spans}.")
    return out


def health_facts(h, who: Subject = SELF) -> list[str]:
    """The planets that are sources of disease and the combinations found, as sentences for the AI (an old text's list, not medical advice)."""
    out = ["Phaladeepika 14 is an old text's list of what planets stand for in sickness. It is not a diagnosis and must not be presented as medical advice."]
    for s in h.sources:
        out.append(f"Phaladeepika {s.verse}: {s.planet.title()} ({'; '.join(s.why)}) stands for: {'; '.join(t for t, _ in s.items)}.")
    out += [f"Phaladeepika {c.verse} ({c.detail}): {c.text}." for c in h.combinations]
    return out


def house_facts(houses, who: Subject = SELF) -> list[str]:
    """What the chapter 15 tests found for each house, as sentences for the AI."""
    return [f"Phaladeepika {f.verse}, the {_ordinal(h.house)} house ({f.detail}): {f.text}." for h in houses for f in h.findings]
