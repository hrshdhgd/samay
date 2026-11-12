"""Brihat Jataka XIV and Phaladeepika 18: what two planets in one sign do, found from a chart.

Texts come from data/rules/conjunctions.yaml. This module loads and validates it and finds the pairs sharing a sign; nothing is
returned until a person has checked the file.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import sign_index

RULES_PATH = DATA_DIR / "rules" / "conjunctions.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")


@dataclass(frozen=True)
class PairText:
    verse_bj: str
    verse_pd: str
    bj: str  # quoted; continues "...the person born will be"
    bj_note: str | None
    pd: str  # paraphrased


@dataclass(frozen=True)
class ConjunctionRules:
    level: str
    checked_by: str | None
    edition: str
    pairs: dict[tuple[str, str], PairText]
    three_bj: str
    three_pd: str

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Together:
    sign: int
    planets: tuple[str, ...]  # in the order Sun..Saturn
    pairs: tuple[tuple[tuple[str, str], PairText], ...]


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> ConjunctionRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    want = {f"{a}+{b}" for a, b in combinations(SEVEN, 2)}
    if set(raw["pairs"]) != want:
        raise ValueError(f"{path.name}: needs exactly the 21 pairs of the seven planets, in the order Sun..Saturn")
    pairs = {}
    for key, p in raw["pairs"].items():
        for field in ("bj", "pd", "verse_bj", "verse_pd"):
            if not isinstance(p.get(field), str) or not p[field].strip():
                raise ValueError(f"{path.name} {key}: needs {field}")
        a, b = key.split("+")
        pairs[a, b] = PairText(p["verse_bj"], p["verse_pd"], p["bj"].strip(), p.get("bj_note"), p["pd"].strip())
    t = raw["three_or_more"]
    return ConjunctionRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], pairs, t["bj"], t["pd"])


def find(rules: ConjunctionRules, chart: Chart) -> tuple[Together, ...]:
    """Each sign holding two or more of the seven planets, with the text for every pair in it. Empty until checked."""
    if not rules.servable:
        return ()
    by_sign: dict[int, list[str]] = {}
    for p in SEVEN:
        by_sign.setdefault(sign_index(chart.planets[p].longitude), []).append(p)
    return tuple(
        Together(sign, tuple(ps), tuple(((a, b), rules.pairs[a, b]) for a, b in combinations(ps, 2)))
        for sign, ps in sorted(by_sign.items()) if len(ps) > 1
    )
