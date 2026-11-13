"""Brihat Jataka chapter XXVII: the figure of each of the 36 drekkanas. Texts in data/rules/brihat-jataka-drekkanas.yaml (quoted); nothing is returned until checked."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-drekkanas.yaml"


@dataclass(frozen=True)
class DrekkanaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    figures: dict[str, list[dict]]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Figure:
    sign: int
    number: int  # 1-3
    lord: str
    verse: str
    text: str
    shape: str | None


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> DrekkanaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if list(raw["figures"]) != SIGNS or any(len(r) != 3 for r in raw["figures"].values()):
        raise ValueError(f"{path.name}: needs three figures for each of the twelve signs, Aries first")
    if any(not (isinstance(f.get("text"), str) and f["text"].strip() and isinstance(f.get("verse"), str)) for r in raw["figures"].values() for f in r):
        raise ValueError(f"{path.name}: every figure needs a verse and a text")
    return DrekkanaRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")), raw["frame"], raw["figures"])


def find(rules: DrekkanaRules, longitude: float) -> Figure | None:
    """The figure of the drekkana a longitude falls in. None until the rules are checked."""
    if not rules.servable:
        return None
    s, n = sign_index(longitude), int(degree_in_sign(longitude) // 10.0)
    row = rules.figures[SIGNS[s]][n]
    return Figure(s, n + 1, SIGN_LORDS[(s + 4 * n) % 12], row["verse"], row["text"], row.get("shape"))
