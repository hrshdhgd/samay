"""Brihat Jataka chapter XX: what the text says about a planet in a house, and how strongly.

Everything comes from data/rules/brihat-jataka-ch20.yaml. The effect texts are quoted from the
public-domain translation; this module only selects the rows that apply to a chart and applies the
text's own strength rule (XX.11). Nothing is generated, and nothing is returned until the rules
file has been checked by a person.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, SIGNS, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-ch20.yaml"
PLANETS = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")  # chapter XX has no Rahu/Ketu
KINDS = ("good", "bad", "mixed")
_SIGN = {name.casefold(): i for i, name in enumerate(SIGNS)}


@dataclass(frozen=True)
class Effect:
    planet: str
    verse: int
    kind: str
    text: str
    variant: str | None = None
    borrowed_from: str | None = None  # "sun" when the text gives this planet the Sun's effects here
    hidden: bool = False  # the checker may hide a row from the family bot


@dataclass(frozen=True)
class Rules:
    level: str
    checked_by: str | None
    edition: str
    exaltation: dict[str, int]
    moolatrikona: dict[str, int]
    friends: dict[str, frozenset[str]]
    neutrals: dict[str, frozenset[str]]
    astangata: dict[str, float]
    astangata_retro: dict[str, float]
    good_share: dict[str, str]
    bad_share: dict[str, str]
    effects: tuple[dict, ...]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Reading:
    planet: str
    house: int
    sign: int
    strength: str  # exaltation, moolatrikona, own, friendly, neutral, inimical or depression
    astangata: bool
    effects: tuple[Effect, ...]
    citation: str
    level: str


def _sign(name: str, where: str) -> int:
    try:
        return _SIGN[name.casefold()]
    except KeyError:
        raise ValueError(f"{where}: unknown sign {name!r}") from None


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> Rules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    s, v = raw["strength"], raw["verification"]
    for i, e in enumerate(raw["effects"]):
        where = f"{path.name} effects[{i}]"
        if e["planet"] not in PLANETS:
            raise ValueError(f"{where}: unknown planet {e['planet']!r}")
        if "same_as" not in e and e.get("kind") not in KINDS:
            raise ValueError(f"{where}: kind must be one of {KINDS}")
        if "same_as" not in e and not e.get("text"):
            raise ValueError(f"{where}: needs a quoted text")
        if not ({"house", "houses", "sign"} & e.keys()):
            raise ValueError(f"{where}: needs house, houses or sign")
        for name in [*e.get("when_lagna", []), *([e["sign"]] if "sign" in e else [])]:
            _sign(name, where)
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    return Rules(
        level=v.get("level", "unchecked"),
        checked_by=v.get("checked_by"),
        edition=raw["edition"],
        exaltation={p: _sign(x, "exaltation") for p, x in s["exaltation"].items()},
        moolatrikona={p: _sign(x, "moolatrikona") for p, x in s["moolatrikona"].items()},
        friends={p: frozenset(x) for p, x in s["friends"].items()},
        neutrals={p: frozenset(x) for p, x in s["neutrals"].items()},
        astangata={p: float(x) for p, x in s["astangata_degrees"].items()},
        astangata_retro={p: float(x) for p, x in s["astangata_degrees_retrograde"].items()},
        good_share=dict(s["good_share"]),
        bad_share=dict(s["bad_share"]),
        effects=tuple(raw["effects"]),
    )


def strength(rules: Rules, planet: str, sign: int) -> str:
    """The planet's standing in a sign, strongest first: exaltation, depression, moolatrikona, own,
    then friendly, neutral or inimical by the sign lord's natural relation to the planet."""
    if rules.exaltation[planet] == sign:
        return "exaltation"
    if (rules.exaltation[planet] + 6) % 12 == sign:
        return "depression"
    if rules.moolatrikona[planet] == sign:
        return "moolatrikona"
    lord = SIGN_LORDS[sign]
    if lord == planet:
        return "own"
    if lord in rules.friends[planet]:
        return "friendly"
    if lord in rules.neutrals[planet]:
        return "neutral"
    return "inimical"


def is_astangata(rules: Rules, planet: str, chart: Chart) -> bool:
    """Within the translator's limit of the Sun, so obscured by its light. The Sun itself never is."""
    if planet not in rules.astangata:
        return False
    p = chart.planets[planet]
    limit = rules.astangata_retro.get(planet, rules.astangata[planet]) if p.retrograde else rules.astangata[planet]
    gap = abs((p.longitude - chart.planets["sun"].longitude + 180.0) % 360.0 - 180.0)
    return gap <= limit


def _rows_for_house(rules: Rules, planet: str, house: int, lagna: int, depth: int = 0) -> list[Effect]:
    rows = [e for e in rules.effects if e["planet"] == planet and (e.get("house") == house or house in e.get("houses", []))]
    borrowed = [e for e in rows if "same_as" in e]
    if borrowed and depth == 0:
        other = borrowed[0]["same_as"]
        return [
            Effect(planet, e.verse, e.kind, e.text, e.variant, borrowed_from=other, hidden=e.hidden)
            for e in _rows_for_house(rules, other, house, lagna, depth + 1)
        ]
    specific = [e for e in rows if "when_lagna" in e and lagna in {_SIGN[s] for s in e["when_lagna"]}]
    chosen = specific or [e for e in rows if "when_lagna" not in e and "same_as" not in e]
    return [Effect(planet, e["verse"], e["kind"], e["text"], e.get("variant"), hidden=bool(e.get("hidden")))
            for e in chosen]


def reading(chart: Chart, planet: str, path: Path = RULES_PATH) -> Reading | None:
    """What chapter XX says about `planet` in this chart, or None if the chapter does not cover the
    planet or the rules have not been checked yet."""
    rules = load_rules(path)
    if planet not in PLANETS or not rules.servable:
        return None
    lagna = sign_index(chart.ascendant)
    sign = sign_index(chart.planets[planet].longitude)
    house = house_from(lagna, sign)
    effects = _rows_for_house(rules, planet, house, lagna)
    effects += [Effect(planet, e["verse"], e["kind"], e["text"], hidden=bool(e.get("hidden")))
                for e in rules.effects if e["planet"] == planet and "sign" in e and _SIGN[e["sign"]] == sign]
    verses = sorted({e.verse for e in effects} | {11})
    citation = f"Brihat Jataka 20.{', 20.'.join(map(str, verses))} ({rules.edition})"
    return Reading(planet, house, sign, strength(rules, planet, sign), is_astangata(rules, planet, chart),
                   tuple(e for e in effects if not e.hidden), citation, rules.level)


def shares(rules: Rules, r: Reading) -> dict[str, str | None]:
    """How much of the good and bad effects the text says come to pass (XX.11 and its note)."""
    key = "astangata" if r.astangata else r.strength
    return {"good": rules.good_share.get(key), "bad": rules.bad_share.get(key)}
