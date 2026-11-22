"""Ashtakavarga: the benefic points each planet gets in each sign, and what the number means (Phaladeepika ch. 23).

The tables are in data/rules/ashtakavarga.yaml and are checked on load against the text's own totals. This module only
counts points from the positions in a chart; the meanings are returned only once a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import sign_index

RULES_PATH = DATA_DIR / "rules" / "ashtakavarga.yaml"
PLANETS = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
)  # Rahu and Ketu have no ashtakavarga
SOURCES = (*PLANETS, "lagna")


@dataclass(frozen=True)
class AshtakavargaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    tables: dict[
        str, dict[str, tuple[int, ...]]
    ]  # planet -> source -> houses (from the source) that give a point
    meaning: dict[int, str]  # number of points -> what the text says
    meaning_verse: str
    threshold: int
    above: str
    below: str
    sarva_verse: str
    variants: tuple[dict, ...]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AshtakavargaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["tables"]) != set(PLANETS) or set(raw["expected"]) != set(PLANETS):
        raise ValueError(f"{path.name}: needs exactly the seven planets")
    tables = {}
    for planet, row in raw["tables"].items():
        if set(row) != set(SOURCES):
            raise ValueError(f"{path.name} {planet}: needs the seven planets and the lagna as sources")
        for src, houses in row.items():
            if houses != sorted(set(houses)) or not all(isinstance(h, int) and 1 <= h <= 12 for h in houses):
                raise ValueError(f"{path.name} {planet} from {src}: houses must be sorted, unique, 1-12")
        want = raw["expected"][planet]
        counts = [len(row[s]) for s in SOURCES]
        if counts != want["counts"] or sum(counts) != want["total"]:
            raise ValueError(
                f"{path.name} {planet}: counts {counts} (total {sum(counts)}) do not match the text's "
                f"{want['counts']} (total {want['total']})"
            )
        tables[planet] = {s: tuple(h) for s, h in row.items()}
    m = raw["points_meaning"]
    s = raw["sarva"]
    return AshtakavargaRules(
        level=v.get("level", "unchecked"),
        checked_by=v.get("checked_by"),
        edition=raw["edition"],
        pages=str(raw.get("pages", "")),
        tables=tables,
        meaning={int(k): str(t) for k, t in m.items() if k != "verse"},
        meaning_verse=str(m["verse"]),
        threshold=int(s["threshold"]),
        above=s["above"],
        below=s["below"],
        sarva_verse=str(s["verse"]),
        variants=tuple(raw.get("variants", ())),
    )


def positions(chart: Chart) -> dict[str, int]:
    """The sign index (0-11) of the seven planets and the lagna at birth."""
    out = {p: sign_index(chart.planets[p].longitude) for p in PLANETS}
    out["lagna"] = sign_index(chart.ascendant)
    return out


def bhinna(rules: AshtakavargaRules, where: dict[str, int]) -> dict[str, list[int]]:
    """Each planet's points in each of the twelve signs (Aries first): one point for every source (a planet or the
    lagna) that has the sign among its benefic houses for that planet."""
    out = {}
    for planet, row in rules.tables.items():
        points = [0] * 12
        for src, houses in row.items():
            for h in houses:
                points[(where[src] + h - 1) % 12] += 1
        out[planet] = points
    return out


def sarva(bhinna_points: dict[str, list[int]]) -> list[int]:
    """The seven planets' points added up for each sign."""
    return [sum(bhinna_points[p][s] for p in PLANETS) for s in range(12)]
