"""Brihat Jataka chapter XIX: the Moon in her sign and navamsa, aspected by the planets.

Texts come from data/rules/brihat-jataka-moon-aspects.yaml. This module loads and validates it, finds which planets aspect the Moon
(by the full aspects of Brihat Jataka II.13) and picks the rows; nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, SIGNS, house_from, navamsa_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-moon-aspects.yaml"
ASPECTING = (
    "sun",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
)  # the six the text lists (the Moon cannot aspect herself)
NAVAMSA_LORDS = ("mars", "venus", "mercury", "moon", "sun", "jupiter", "saturn")


@dataclass(frozen=True)
class AspectRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    full: dict[str, tuple[int, ...]]
    aspect_text: str
    degree_text: str
    degree_rising: str
    signs: dict[str, dict[str, str]]
    navamsas: dict[str, dict[str, str]]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class MoonAspects:
    sign: str
    navamsa_sign: str
    navamsa_lord: str
    aspecting: tuple[str, ...]  # the planets that aspect the Moon, in the order Sun..Saturn
    in_sign: tuple[tuple[str, str], ...]  # (planet, text) for the Moon's sign
    in_navamsa: tuple[tuple[str, str], ...]  # (planet, text) for her navamsa


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AspectRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if list(raw["signs"]) != SIGNS:
        raise ValueError(f"{path.name}: signs must be the twelve, Aries first")
    for table, keys in (("signs", list(SIGNS)), ("navamsas", list(NAVAMSA_LORDS))):
        if list(raw[table]) != keys:
            raise ValueError(f"{path.name}: {table} must be {keys}")
        for k, row in raw[table].items():
            if set(row) != set(ASPECTING) or not all(isinstance(t, str) and t.strip() for t in row.values()):
                raise ValueError(f"{path.name} {table}.{k}: needs a text for each of {ASPECTING}")
    rule = raw["aspect_rule"]
    full = {p: tuple(h) for p, h in rule["full"].items()}
    if set(full) != {
        "sun",
        "moon",
        "mars",
        "mercury",
        "jupiter",
        "venus",
        "saturn",
    } or any(7 not in h for h in full.values()):
        raise ValueError(f"{path.name}: every planet fully aspects the 7th")
    return AspectRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        full,
        rule["text"],
        raw["degree"]["text"],
        raw["degree"]["rising_sign"],
        {k: dict(r) for k, r in raw["signs"].items()},
        {k: dict(r) for k, r in raw["navamsas"].items()},
    )


def find(rules: AspectRules, chart: Chart) -> MoonAspects | None:
    """Which planets aspect the Moon, with the text for her sign and for her navamsa. None until the rules are checked."""
    if not rules.servable:
        return None
    moon_lon = chart.planets["moon"].longitude
    moon_sign = sign_index(moon_lon)
    nav = navamsa_sign(moon_lon)
    lord = SIGN_LORDS[nav]
    aspecting = tuple(
        p for p in ASPECTING if house_from(sign_index(chart.planets[p].longitude), moon_sign) in rules.full[p]
    )
    return MoonAspects(
        SIGNS[moon_sign],
        SIGNS[nav],
        lord,
        aspecting,
        tuple((p, rules.signs[SIGNS[moon_sign]][p]) for p in aspecting),
        tuple((p, rules.navamsas[lord][p]) for p in aspecting),
    )
