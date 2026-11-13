"""Phaladeepika chapter 4 (Mantreswara's verses 1-8): the six kinds of strength of a planet, as yes-or-no tests.

Texts and definitions come from data/rules/phaladeepika-ch4-strength.yaml (paraphrased); the tests are coded here. This is a count of the book's simple
conditions, not the full shadbala arithmetic. Nothing is returned until a person has checked the file.
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
from .vedic import SIGNS, degree_in_sign, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch4-strength.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
KINDS = ("kala", "chesta", "uchcha", "dik", "ayana", "sthana")
NATURAL_ORDER = ("sun", "moon", "venus", "jupiter", "mercury", "mars", "saturn")
DEEP_EXALTATION = {"sun": 10.0, "moon": 33.0, "mars": 298.0, "mercury": 165.0, "jupiter": 95.0, "venus": 357.0, "saturn": 200.0}
DAY_PLANETS, NIGHT_PLANETS = ("sun", "jupiter", "saturn"), ("moon", "mars", "venus")
SOUTH_PLANETS = ("mercury", "saturn", "moon")
DIK_HOUSE = {"sun": 10, "mars": 10, "mercury": 1, "jupiter": 1, "saturn": 7, "moon": 4, "venus": 4}
GOOD_SIGNS = ("exaltation", "moolatrikona", "own", "friendly")


@dataclass(frozen=True)
class StrengthRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    order_note: str
    kinds: dict[str, dict]
    modifiers: dict
    nodes: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class PlanetStrength:
    planet: str
    held: dict[str, float]  # kind -> 0, 0.5 or 1
    notes: tuple[str, ...]
    total: float


@dataclass(frozen=True)
class Strengths:
    planets: tuple[PlanetStrength, ...]
    strongest: tuple[str, ...]
    weakest: tuple[str, ...]
    nodes: tuple[str, ...]  # sentences about Rahu and Ketu


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> StrengthRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["kinds"]) != set(KINDS):
        raise ValueError(f"{path.name}: kinds must be exactly {KINDS}")
    for k, d in raw["kinds"].items():
        if not all(isinstance(d.get(f), str) and d[f].strip() for f in ("verse", "name", "definition", "text")):
            raise ValueError(f"{path.name} {k}: needs verse, name, definition and text")
    return StrengthRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")), raw["frame"], raw["order_note"],
                         raw["kinds"], raw["modifiers"], raw["nodes"])


def find(rules: StrengthRules, chart: Chart, night: bool | None) -> Strengths | None:
    """Which of the six strengths each planet has. `night` is None when the Sun does not both rise and set (the time-of-day test is then skipped).
    None until the rules are checked."""
    if not rules.servable:
        return None
    ch20 = house_effects.load_rules()
    lagna = sign_index(chart.ascendant)
    elong = (chart.planets["moon"].longitude - chart.planets["sun"].longitude) % 360.0
    bright = elong < 180.0
    full_moon = 144.0 <= elong <= 216.0
    out = []
    for p in SEVEN:
        pl = chart.planets[p]
        sign = sign_index(pl.longitude)
        house = house_from(lagna, sign)
        stand = house_effects.strength(ch20, p, sign)
        combust = house_effects.is_astangata(ch20, p, chart)
        tropical = (pl.longitude + chart.ayanamsa) % 360.0
        north = 0.0 < tropical < 180.0
        held: dict[str, float] = {}
        notes: list[str] = []
        # kala: two half-points
        k = 0.0
        if night is not None:
            suits_time = p == "mercury" or (night and p in NIGHT_PLANETS) or (not night and p in DAY_PLANETS)
            if suits_time:
                k += 0.5
        # the bright half suits the benefics (Mercury, Jupiter, Venus) and the Moon when she waxes; the dark half suits the Sun, Mars and Saturn
        if (bright if p == "moon" else (p in ("mercury", "jupiter", "venus")) == bright):
            k += 0.5
        held["kala"] = k
        # chesta
        held["chesta"] = 1.0 if (full_moon if p == "moon" else north if p == "sun" else pl.retrograde) else 0.0
        # uchcha
        dist = abs((pl.longitude - DEEP_EXALTATION[p] + 180.0) % 360.0 - 180.0)
        frac = (180.0 - dist) / 180.0
        held["uchcha"] = 1.0 if frac >= 2 / 3 else 0.0
        notes.append(f"{round(100 * frac)}% of the way to full exaltation")
        # dik
        held["dik"] = 1.0 if house == DIK_HOUSE[p] else 0.0
        # ayana
        held["ayana"] = 1.0 if (north != (p in SOUTH_PLANETS)) else 0.0
        # sthana
        held["sthana"] = 0.0 if (stand == "depression" or combust) else 1.0 if (stand in GOOD_SIGNS or house in (1, 4, 7, 10)) else 0.0
        if combust:
            notes.append(rules.modifiers["combust"])
        if stand == "depression" and pl.retrograde and not combust:
            notes.append(rules.modifiers["retrograde_debilitated"])
        out.append(PlanetStrength(p, held, tuple(notes), sum(held.values())))
    best = max(s.total for s in out)
    worst = min(s.total for s in out)
    n = rules.nodes
    rahu, ketu = SIGNS[sign_index(chart.planets["rahu"].longitude)], SIGNS[sign_index(chart.planets["ketu"].longitude)]
    ketu_lon = chart.planets["ketu"].longitude
    ketu_ok = ketu in n["ketu_strong_in"] or (ketu == "Sagittarius" and degree_in_sign(ketu_lon) >= 15.0)
    nodes = (f"Rahu is in {rahu}: " + ("strong there" if rahu in n["rahu_strong_in"] else "not one of the signs where the book calls it strong"),
             f"Ketu is in {ketu}: " + ("strong there" if ketu_ok else "not one of the signs where the book calls it strong"))
    return Strengths(tuple(out), tuple(s.planet for s in out if s.total == best), tuple(s.planet for s in out if s.total == worst), nodes)
