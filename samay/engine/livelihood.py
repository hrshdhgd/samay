"""Brihat Jataka chapter X: the source of wealth and the kind of work, from the 10th house.

Texts are in data/rules/brihat-jataka-livelihood.yaml (quoted from the public-domain translation). Nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import house_effects
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, SIGNS, house_from, navamsa_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-livelihood.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")


@dataclass(frozen=True)
class LivelihoodRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    wealth: dict
    fallback: dict
    avocation: dict
    yoga: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Livelihood:
    wealth: tuple[
        tuple[str, str, str], ...
    ]  # (verse, from where, text): the planets in the 10th from the lagna and from the Moon
    work: tuple[
        tuple[str, str, str], ...
    ]  # (verse, via, text): the navamsa-lord route, when no planet is in either 10th
    conditions: tuple[
        tuple[str, str], ...
    ]  # (verse, text): verse 4 for each yoga planet and the benefics rule
    notes: tuple[str, ...]

    def grouped_work(self) -> tuple[tuple[str, tuple[str, ...], str], ...]:
        """Group identical interpretations while preserving every chart route."""
        groups: dict[tuple[str, str], list[str]] = {}
        for verse, route, text in self.work:
            groups.setdefault((verse, text), []).append(route)
        return tuple(
            (verse, tuple(routes), text) for (verse, text), routes in groups.items()
        )


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> LivelihoodRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    for key in ("source_of_wealth", "avocation"):
        if not set(SEVEN) <= set(raw[key]) or not all(
            isinstance(raw[key][p], str) and raw[key][p].strip() for p in SEVEN
        ):
            raise ValueError(
                f"{path.name} {key}: needs a text for each of the seven planets"
            )
    for k in (
        "friendly_sign",
        "inimical_sign",
        "own_sign",
        "sun_exalted",
        "benefics_prosper",
    ):
        if not raw["yoga_planet"].get(k):
            raise ValueError(f"{path.name}: yoga_planet needs {k}")
    return LivelihoodRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["source_of_wealth"],
        raw["fallback"],
        raw["avocation"],
        raw["yoga_planet"],
    )


def find(rules: LivelihoodRules, chart: Chart) -> Livelihood | None:
    """The source of wealth and the work chapter X points to. None until the rules are checked."""
    if not rules.servable:
        return None
    ch20 = house_effects.load_rules()
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in SEVEN}
    moon = sign["moon"]
    tenth = {"the lagna": (lagna + 9) % 12, "the Moon": (moon + 9) % 12}
    wealth: list[tuple[str, str, str]] = []
    yoga: list[str] = []
    for where, s in tenth.items():
        for p in SEVEN:
            if sign[p] == s:
                wealth.append(
                    (
                        rules.wealth["verse"],
                        f"{p.title()} is in the 10th from {where}",
                        f"{rules.wealth['lead']} {rules.wealth[p]}",
                    )
                )
                yoga.append(p)
    work: list[tuple[str, str, str]] = []
    notes: list[str] = []
    if len(wealth) > 1:
        notes.append(rules.wealth["both_note"])
    if not wealth:
        sun_sign = sign["sun"]
        for where, s in (
            ("the lagna", tenth["the lagna"]),
            ("the Moon", tenth["the Moon"]),
            ("the Sun", (sun_sign + 9) % 12),
        ):
            lord = SIGN_LORDS[s]
            nav_lord = SIGN_LORDS[navamsa_sign(chart.planets[lord].longitude)]
            work.append(
                (
                    rules.avocation["verse"],
                    f"the 10th from {where} is {SIGNS[s]}, ruled by {lord.title()}, which is in the navamsa of {nav_lord.title()}",
                    f"A person will {rules.avocation[nav_lord]}",
                )
            )
            yoga.append(nav_lord)
        notes.append(rules.fallback["text"])
    conditions: list[tuple[str, str]] = []
    for p in dict.fromkeys(yoga):
        stand = house_effects.strength(ch20, p, sign[p])
        key = {
            "friendly": "friendly_sign",
            "inimical": "inimical_sign",
            "own": "own_sign",
            "moolatrikona": "own_sign",
        }.get(stand)
        if p == "sun" and stand == "exaltation":
            key = "sun_exalted"
        if key:
            conditions.append(
                (rules.yoga["verse"], f"{p.title()} ({stand} sign): {rules.yoga[key]}")
            )
    if any(house_from(lagna, sign[b]) in (11, 1, 2) for b in BENEFICS):
        conditions.append((rules.yoga["verse"], rules.yoga["benefics_prosper"]))
    return Livelihood(tuple(wealth), tuple(work), tuple(conditions), tuple(notes))
