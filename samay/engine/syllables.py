"""Naming syllable for a Moon position: the sound a name traditionally begins with (the Avakahada chakra).

The table is data/nakshatra_syllables.yaml (two modern sources, in agreement on all 108 padas; some padas have
readings that other panchanga traditions use, listed as `also`). The Moon's nakshatra and pada come from
vedic.nakshatra.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .paths import DATA_DIR
from .vedic import NAKSHATRAS, nakshatra

TABLE = DATA_DIR / "nakshatra_syllables.yaml"


@dataclass(frozen=True)
class Syllable:
    nakshatra: str
    pada: int
    syllable: str
    devanagari: str
    also: tuple[str, ...] = ()

    def __str__(self) -> str:
        more = f" (other traditions also use {', '.join(self.also)})" if self.also else ""
        return f"{self.syllable}{more}"


@lru_cache(maxsize=2)
def load_table(path: Path = TABLE) -> dict[tuple[str, int], Syllable]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    table: dict[tuple[str, int], Syllable] = {}
    for row in raw:
        for pada, p in enumerate(row["padas"], start=1):
            for field in (p["syllable"], p["devanagari"], *p.get("also", ())):
                if not isinstance(field, str):  # e.g. a bare `No` is read by YAML as False
                    raise TypeError(f"{path.name}: {row['nakshatra']} pada {pada}: {field!r} must be quoted text")
            table[(row["nakshatra"], pada)] = Syllable(
                row["nakshatra"], pada, p["syllable"], p["devanagari"], tuple(p.get("also", ())))
    if len(table) != 108 or {n for n, _ in table} != set(NAKSHATRAS):
        raise ValueError(f"{path.name}: expected 27 nakshatras with 4 padas each")
    return table


def naming_syllable(moon_longitude: float) -> Syllable:
    """The syllable for the pada the Moon (sidereal longitude, degrees) was in."""
    index, pada = nakshatra(moon_longitude)
    return load_table()[(NAKSHATRAS[index], pada)]
