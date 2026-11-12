"""Brihat Jataka XVI and XVII: what the text says of a person by the nakshatra and sign the Moon holds at birth.

Everything comes from data/rules/brihat-jataka-moon.yaml (quoted from the public-domain translation). This module loads
and validates it and picks the two rows for a Moon longitude; nothing is returned until a person has checked the file.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .paths import DATA_DIR
from .vedic import SIGNS, nakshatra, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-moon.yaml"
# The translation's spelling of the 27 nakshatras, in the order of vedic.NAKSHATRAS (Ashwini first).
TRANSLATION_NAMES = (
    "Aswini", "Bharani", "Krittika", "Rohini", "Mrigasirsha", "Ardra", "Punarvasu", "Pushya", "Aslesha", "Magha",
    "P. Phalguni", "U. Phalguni", "Hasta", "Chittra", "Swati", "Visakha", "Anuradha", "Jyeshta", "Moola", "P. Ashadha",
    "U. Ashadha", "Sravana", "Dhanishta", "Satabhishak", "P. Bhadrapada", "U. Bhadrapada", "Revati",
)


@dataclass(frozen=True)
class Description:
    name: str  # the translation's spelling
    verse: int
    text: str  # quoted; continues "A person born with the Moon in ..."


@dataclass(frozen=True)
class MoonRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    nakshatras: tuple[Description, ...]
    signs: tuple[Description, ...]
    conditions: dict[str, tuple[str, str]]  # name -> (verse, text)

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> MoonRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    for key, want in (("nakshatras", 27), ("signs", 12)):
        if len(raw[key]) != want:
            raise ValueError(f"{path.name}: needs {want} {key}, has {len(raw[key])}")
    for i, row in enumerate(raw["signs"]):
        if row["name"] != SIGNS[i]:
            raise ValueError(f"{path.name}: sign {i + 1} is {row['name']!r}, expected {SIGNS[i]!r}")
    for i, row in enumerate(raw["nakshatras"]):
        if row["name"] != TRANSLATION_NAMES[i]:
            raise ValueError(f"{path.name}: nakshatra {i + 1} is {row['name']!r}, expected {TRANSLATION_NAMES[i]!r}")
    for row in (*raw["nakshatras"], *raw["signs"]):
        if not isinstance(row["text"], str) or not row["text"].strip() or not isinstance(row["verse"], int):
            raise ValueError(f"{path.name}: every row needs a text and a verse number")
    return MoonRules(
        level=v.get("level", "unchecked"), checked_by=v.get("checked_by"), edition=raw["edition"],
        pages=str(raw.get("pages", "")),
        nakshatras=tuple(Description(r["name"], r["verse"], r["text"].strip()) for r in raw["nakshatras"]),
        signs=tuple(Description(r["name"], r["verse"], r["text"].strip()) for r in raw["signs"]),
        conditions={k: (c["verse"], c["text"]) for k, c in raw["conditions"].items()},
    )


def for_moon(rules: MoonRules, longitude: float) -> tuple[int, Description, int, Description, int]:
    """(sign index, the sign's description, nakshatra index, its description, pada 1-4) for a sidereal Moon longitude."""
    sign = sign_index(longitude)
    nak, pada = nakshatra(longitude)
    return sign, rules.signs[sign], nak, rules.nakshatras[nak], pada
