"""Phaladeepika chapter 20: what a planet's dasha brings through the house(s) it rules, strong or weak.

Texts come from data/rules/phaladeepika-ch20-lordship.yaml (paraphrased). This module computes, from a chart, which houses a planet
rules, where it stands, and which of verse 14's conditions it meets; nothing is returned until a person has checked the file.
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
from .vedic import DASHA_YEARS, SIGN_LORDS, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch20-lordship.yaml"
PLANETS = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
)  # Rahu and Ketu rule no house in this chapter


@dataclass(frozen=True)
class LordshipRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    houses: dict[int, dict[str, tuple[int, str]]]  # house -> {"strong"|"weak": (verse, text)}
    good_condition: str
    weak_condition: str
    nature: dict
    troublesome: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Verdict:
    planet: str
    owned: tuple[int, ...]  # houses from the lagna that the planet rules
    house: int  # the house it stands in
    good: tuple[str, ...]  # verse 14's good conditions the chart meets
    adverse: tuple[str, ...]  # verse 14's adverse conditions the chart meets
    leaning: str  # "strong", "weak", or "undecided"
    rows: tuple[
        tuple[int, str, int, str], ...
    ]  # (house, "strong"|"weak"|"both", verse, text), in house order
    nature: tuple[tuple[int, str], ...] = ()  # verse 41: (verse, statement) the chart meets
    troublesome: tuple[tuple[int, str], ...] = ()  # verse 24: (verse, statement) the chart meets


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> LordshipRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["houses"]) != set(range(1, 13)):
        raise ValueError(f"{path.name}: needs all twelve houses")
    houses = {}
    for h, row in raw["houses"].items():
        if set(row) != {"strong", "weak"}:
            raise ValueError(f"{path.name} house {h}: needs a strong and a weak result")
        for kind, e in row.items():
            if (
                not isinstance(e.get("verse"), int)
                or not isinstance(e.get("text"), str)
                or not e["text"].strip()
            ):
                raise ValueError(f"{path.name} house {h} {kind}: needs a verse number and a text")
        houses[int(h)] = {k: (e["verse"], e["text"].strip()) for k, e in row.items()}
    return LordshipRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        houses,
        raw["condition"]["good"],
        raw["condition"]["weak"],
        _nature(raw, path),
        raw["troublesome"],
    )


def _nature(raw: dict, path: Path) -> dict:
    n = raw["nature"]
    for key, s in n["statements"].items():
        if (
            s["who"] not in ("any", "benefic", "malefic")
            or not s.get("text")
            or not (("owns" in s) ^ ("owns_all" in s))
        ):
            raise ValueError(f"{path.name} nature.{key}: needs text, who and exactly one of owns / owns_all")
        if not all(1 <= h <= 12 for h in s.get("owns", s.get("owns_all"))):
            raise ValueError(f"{path.name} nature.{key}: houses must be 1-12")
    t = raw["troublesome"]
    if not set(t["by_order"]) <= {*PLANETS, "rahu", "ketu"} or not all(
        1 <= v <= 9 for v in t["by_order"].values()
    ):
        raise ValueError(f"{path.name} troublesome.by_order: planets and positions 1-9")
    return n


def natural_benefic(chart: Chart, planet: str) -> bool:
    """Jupiter, Venus, Mercury and the waxing Moon are benefic; the others malefic (a reading, see the rules file)."""
    if planet == "moon":
        return (chart.planets["moon"].longitude - chart.planets["sun"].longitude) % 360.0 < 180.0
    return planet in ("jupiter", "venus", "mercury")


def judge(rules: LordshipRules, chart: Chart, planet: str, birth_lord: str | None = None) -> Verdict | None:
    """The houses `planet` rules in this chart, and how well placed it is by verse 14. None while the rules are
    unchecked, for Rahu and Ketu, and for a planet that rules no house of this chart."""
    if not rules.servable or planet not in PLANETS:
        return None
    lagna = sign_index(chart.ascendant)
    owned = tuple(h for h in range(1, 13) if SIGN_LORDS[(lagna + h - 1) % 12] == planet)
    if not owned:
        return None
    sign = sign_index(chart.planets[planet].longitude)
    house = house_from(lagna, sign)
    ch = house_effects.load_rules()
    standing = house_effects.strength(ch, planet, sign)
    good, adverse = [], []
    if house in (6, 8, 12):
        adverse.append(f"in the {house}th house")
    if standing == "inimical":
        adverse.append("in an inimical sign")
    if standing == "depression":
        adverse.append("in its sign of debilitation")
    if house_effects.is_astangata(ch, planet, chart):
        adverse.append("eclipsed by the Sun's rays")
    if standing in ("own", "moolatrikona"):
        good.append("in its own sign")
    if standing == "exaltation":
        good.append("in its sign of exaltation")
    if chart.planets[planet].retrograde:
        good.append("retrograde")
    leaning = "weak" if adverse else "strong" if good else "undecided"
    rows = []
    for h in owned:
        kinds = ("strong", "weak") if leaning == "undecided" else (leaning,)
        for kind in kinds:
            verse, text = rules.houses[h][kind]
            rows.append((h, kind, verse, text))
    benefic = natural_benefic(chart, planet)
    nature = []
    for s in rules.nature["statements"].values():
        if s["who"] == "benefic" and not benefic or s["who"] == "malefic" and benefic:
            continue
        if "only" in s and planet not in s["only"]:
            continue
        need = s.get("owns_all")
        if (
            need is not None
            and not set(need) <= set(owned)
            or need is None
            and not set(s["owns"]) & set(owned)
        ):
            continue
        nature.append((rules.nature["verse"], s["text"]))
    t = rules.troublesome
    trouble = []
    if birth_lord is not None and planet in t["by_order"]:
        order = list(DASHA_YEARS)
        position = (order.index(planet) - order.index(birth_lord)) % 9 + 1
        if position == t["by_order"][planet]:
            trouble.append(
                (
                    t["verse"],
                    t["by_order_text"].format(planet=planet.title(), n=position),
                )
            )
    if chart.planets[planet].longitude % 30.0 >= t["last_degree_from"]:
        trouble.append((t["verse"], t["last_degree_text"]))
    if set(t["houses"]) & set(owned):
        trouble.append((t["verse"], t["house_text"]))
    return Verdict(
        planet,
        owned,
        house,
        tuple(good),
        tuple(adverse),
        leaning,
        tuple(rows),
        tuple(nature),
        tuple(trouble),
    )
