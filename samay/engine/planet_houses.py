"""Phaladeepika chapter 8: what a planet does in each house from the lagna. A second voice next to Brihat Jataka XX.

Everything the text says comes from data/rules/phaladeepika-ch8-planets-in-houses.yaml. This module loads and validates
it and picks the rows that apply to a rising sign; nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .paths import DATA_DIR
from .vedic import SIGNS

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch8-planets-in-houses.yaml"
PLANETS = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
    "rahu",
    "ketu",
)
_SIGN = {name.casefold(): i for i, name in enumerate(SIGNS)}


@dataclass(frozen=True)
class Row:
    text: str
    when_lagna: frozenset[int] = frozenset()  # rising signs the row is only for
    unless_lagna: frozenset[int] = frozenset()  # rising signs the row is not for

    def applies(self, lagna: int) -> bool:
        return (not self.when_lagna or lagna in self.when_lagna) and lagna not in self.unless_lagna


@dataclass(frozen=True)
class PlanetHouseRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    verses: dict[str, str]  # planet -> "1-4"
    rows: dict[tuple[str, int], tuple[Row, ...]]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS

    def lookup(self, planet: str, house: int, lagna: int) -> tuple[tuple[Row, ...], str] | None:
        """The rows that apply for this planet, house and rising sign (index 0-11), and the text's verse range;
        None while the rules are unchecked or when no row applies."""
        if not self.servable:
            return None
        rows = tuple(r for r in self.rows.get((planet, house), ()) if r.applies(lagna))
        return (rows, self.verses[planet]) if rows else None


def _signs(names, where: str) -> frozenset[int]:
    try:
        return frozenset(_SIGN[str(n).casefold()] for n in names)
    except KeyError as e:
        raise ValueError(f"{where}: unknown sign {e.args[0]!r}") from None


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> PlanetHouseRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rows, verses = {}, {}
    for planet, block in raw["effects"].items():
        if planet not in PLANETS:
            raise ValueError(f"{path.name}: unknown planet {planet!r}")
        verses[planet] = str(block["verse"])
        if set(block["houses"]) != set(range(1, 13)):
            raise ValueError(f"{path.name} {planet}: needs all twelve houses")
        for house, spec in block["houses"].items():
            where = f"{path.name} {planet} house {house}"
            specs = [spec] if isinstance(spec, str) else spec
            built = []
            for s in specs:
                s = {"text": s} if isinstance(s, str) else s
                if not isinstance(s.get("text"), str) or not s["text"].strip():
                    raise ValueError(f"{where}: every row needs a text")
                built.append(
                    Row(
                        s["text"].strip(),
                        _signs(s.get("when_lagna", ()), where),
                        _signs(s.get("unless_lagna", ()), where),
                    )
                )
            rows[planet, int(house)] = tuple(built)
    if set(verses) != set(PLANETS):
        raise ValueError(f"{path.name}: needs all nine planets")
    return PlanetHouseRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        verses,
        rows,
    )
