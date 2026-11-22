"""Phaladeepika chapter 21: what each antardasha (sub-chapter) brings in each mahadasha.

Everything the text says comes from data/rules/phaladeepika-ch21-antardasha.yaml. This module only loads and validates
it and looks up a pair; nothing is returned until the rules file has been checked by a person.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .paths import DATA_DIR
from .vedic import DASHA_YEARS

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch21-antardasha.yaml"
LORDS = tuple(DASHA_YEARS)  # the nine dasha lords


@dataclass(frozen=True)
class AntardashaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    effects: dict[tuple[str, str], tuple[str, int]]  # (mahadasha lord, antardasha lord) -> (text, verse)

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS

    def result(self, maha: str, antar: str) -> tuple[str, int] | None:
        """The text's result for this pair, or None when the rules are unchecked or the text gives none."""
        return self.effects.get((maha, antar)) if self.servable else None


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AntardashaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    effects, seen_verses = {}, {}
    for maha, row in raw["effects"].items():
        if maha not in LORDS:
            raise ValueError(f"{path.name}: unknown mahadasha lord {maha!r}")
        for antar, e in row.items():
            where = f"{path.name} effects.{maha}.{antar}"
            if antar not in LORDS:
                raise ValueError(f"{where}: unknown antardasha lord")
            text, verse = e.get("text"), e.get("verse")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{where}: needs a text")
            if not isinstance(verse, int):
                raise TypeError(f"{where}: needs a verse number")
            if verse in seen_verses:
                raise ValueError(f"{where}: verse {verse} is already used by {seen_verses[verse]}")
            seen_verses[verse] = f"{maha}.{antar}"
            effects[(maha, antar)] = (text.strip(), verse)
    return AntardashaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        effects,
    )
