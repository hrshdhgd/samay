"""Brihat Jataka chapter XVIII: what a person is like with the Sun, Mars, Mercury, Jupiter, Venus or Saturn in a given sign.

Texts are in data/rules/brihat-jataka-planets-in-signs.yaml (quoted from the public-domain translation). Nothing is returned until a person has checked the file.
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
from .vedic import SIGNS, degree_in_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-planets-in-signs.yaml"
PLANETS = ("sun", "mars", "mercury", "jupiter", "venus", "saturn")


@dataclass(frozen=True)
class SignRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    planets: dict[str, dict[str, dict]]
    sun_exalt: dict
    condition: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Reading:
    planet: str
    sign: int
    verse: str
    text: str  # quoted; continues "A person born with the <planet> in <sign> will be"
    strength: str  # the planet's standing in that sign (Brihat Jataka chapter 20), the text's own measure of how much comes to pass
    note: str = ""


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> SignRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["planets"]) != set(PLANETS):
        raise ValueError(f"{path.name}: needs exactly {PLANETS}")
    for p, row in raw["planets"].items():
        if list(row) != SIGNS:
            raise ValueError(f"{path.name} {p}: needs the twelve signs, Aries first")
        for s, r in row.items():
            if not (isinstance(r.get("text"), str) and r["text"].strip() and isinstance(r.get("verse"), str)):
                raise ValueError(f"{path.name} {p} {s}: needs a verse and a text")
    return SignRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["planets"],
        raw["sun_exaltation_degree"],
        raw["condition"],
    )


def find(rules: SignRules, chart: Chart, moon_cancer_text: str | None = None) -> tuple[Reading, ...] | None:
    """The chapter XVIII reading for each of the six planets in its sign. None until the rules are checked. `moon_cancer_text` is chapter XVII's text for the Moon
    in Cancer, which the Aquarius row for Jupiter refers to."""
    if not rules.servable:
        return None
    ch20 = house_effects.load_rules()
    out = []
    for p in PLANETS:
        lon = chart.planets[p].longitude
        sign = sign_index(lon)
        row = rules.planets[p][SIGNS[sign]]
        text, note = row["text"], ""
        if (
            p == "sun"
            and sign == 0
            and rules.sun_exalt["from_degree"] <= degree_in_sign(lon) < rules.sun_exalt["to_degree"]
        ):
            text, note = (
                rules.sun_exalt["text"],
                f"the Sun is in the exaltation degree ({rules.sun_exalt['verse']})",
            )
        if p == "jupiter" and sign == 10 and moon_cancer_text:
            note = f"the text says: {text}. Chapter XVII's text for the Moon in Cancer reads: a person born with it {moon_cancer_text}"
        out.append(Reading(p, sign, row["verse"], text, house_effects.strength(ch20, p, sign), note))
    return tuple(out)
