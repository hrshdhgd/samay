"""Phaladeepika chapter 9: what each rising sign says of a person. Texts are in data/rules/phaladeepika-ch9-ascendants.yaml (paraphrased); nothing is returned until checked."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .paths import DATA_DIR
from .vedic import SIGNS

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch9-ascendants.yaml"


@dataclass(frozen=True)
class AscendantRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    moon_rule: dict
    signs: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS

    def text(self, sign: int) -> tuple[str, str] | None:
        """(verse, text) for a rising sign index, or None until the rules are checked."""
        return (
            (self.signs[SIGNS[sign]]["verse"], self.signs[SIGNS[sign]]["text"])
            if self.servable
            else None
        )


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AscendantRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if list(raw["signs"]) != SIGNS:
        raise ValueError(f"{path.name}: needs the twelve signs, Aries first")
    for s, row in raw["signs"].items():
        if not (
            isinstance(row.get("text"), str)
            and row["text"].strip()
            and isinstance(row.get("verse"), str)
        ):
            raise ValueError(f"{path.name} {s}: needs a verse and a text")
    return AscendantRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw["moon_rule"],
        raw["signs"],
    )
