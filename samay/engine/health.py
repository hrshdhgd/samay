"""Phaladeepika chapter 14, verses 1-11: the planets as sources of disease, and the book's specific combinations.

Texts come from data/rules/phaladeepika-ch14-health.yaml (paraphrased). This module loads and validates it and decides, from a chart, which
planets are sources of disease and which combinations hold. It is an old text's list, never a diagnosis. Nothing is returned until the file
has been checked by a person.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch14-health.yaml"
BODIES = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
MALEFICS = ("sun", "mars", "saturn", "rahu", "ketu")
FULL_ASPECTS = {"mars": (4, 7, 8), "jupiter": (5, 7, 9), "saturn": (3, 7, 10)}  # Brihat Jataka II.13; every other body the 7th
WATERY = {3, 7, 11}  # Cancer, Scorpio, Pisces
COMBINATIONS = (
    "eye_right", "eye_left", "ear", "stomach", "rectal", "private_parts", "occupant_sun", "occupant_mars_ketu", "occupant_venus",
    "occupant_jupiter", "occupant_saturn", "rahu_mars", "saturn_moon", "waning_moon_water",
)


@dataclass(frozen=True)
class HealthRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    caution: str
    sources_text: str
    sources_verse: str
    planets: dict[str, dict]
    combinations: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Source:
    planet: str
    why: tuple[str, ...]  # "in the 6th house", "lord of the 6th", "joined with the lord of the 6th"
    verse: str
    items: tuple[tuple[str, tuple[str, ...]], ...]  # (trouble, tags)


@dataclass(frozen=True)
class Combination:
    key: str
    verse: str
    text: str
    detail: str


@dataclass(frozen=True)
class Health:
    sources: tuple[Source, ...]
    overlaps: tuple[tuple[str, tuple[str, ...]], ...]  # (tag, planets whose lists carry it), where two or more sources agree
    combinations: tuple[Combination, ...]


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> HealthRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["planets"]) != set(BODIES):
        raise ValueError(f"{path.name}: needs all nine planets")
    for p, block in raw["planets"].items():
        if not block.get("items") or not all(isinstance(i.get("text"), str) and i["text"].strip() for i in block["items"]):
            raise ValueError(f"{path.name} {p}: needs a list of troubles")
    if set(raw["combinations"]) != set(COMBINATIONS):
        raise ValueError(f"{path.name}: combinations must be exactly {COMBINATIONS}")
    for k, c in raw["combinations"].items():
        if not all(isinstance(c.get(f), str) and c[f].strip() for f in ("verse", "definition", "text")):
            raise ValueError(f"{path.name} {k}: needs verse, definition and text")
    return HealthRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")), raw["caution"],
                       raw["sources"]["text"], raw["sources"]["verse"], raw["planets"], raw["combinations"])


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def find(rules: HealthRules, chart: Chart) -> Health | None:
    """The planets that are sources of disease in this chart, where their lists agree, and the book's specific combinations. None until checked."""
    if not rules.servable:
        return None
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
    house = {p: house_from(lagna, s) for p, s in sign.items()}
    lord = {h: SIGN_LORDS[(lagna + h - 1) % 12] for h in (6, 8)}

    def aspected_by(target_sign: int, by: tuple[str, ...]) -> list[str]:
        return [p for p in by if p in sign and sign[p] != target_sign
                and house_from(sign[p], target_sign) in FULL_ASPECTS.get(p, (7,))]

    def joined_or_aspected(p: str, by: tuple[str, ...]) -> bool:
        return any(sign[q] == sign[p] for q in by if q != p) or bool(aspected_by(sign[p], by))

    why: dict[str, list[str]] = {}
    for p in BODIES:
        if house[p] in (6, 8, 12):
            why.setdefault(p, []).append(f"in the {_ord(house[p])} house")
    why.setdefault(lord[6], []).append("lord of the 6th")
    for p in BODIES:
        if p != lord[6] and sign[p] == sign[lord[6]]:
            why.setdefault(p, []).append(f"joined with the 6th lord {lord[6].title()}")
    sources = tuple(
        Source(p, tuple(w), rules.planets[p]["verse"], tuple((i["text"], tuple(i.get("tags", ()))) for i in rules.planets[p]["items"]))
        for p, w in sorted(why.items(), key=lambda kv: BODIES.index(kv[0]))
    )
    count: dict[str, list[str]] = {}
    for s in sources:
        for tag in {t for _, tags in s.items for t in tags}:
            count.setdefault(tag, []).append(s.planet)
    overlaps = tuple((t, tuple(ps)) for t, ps in sorted(count.items()) if len(ps) >= 2)

    found: list[Combination] = []

    def add(key: str, detail: str) -> None:
        c = rules.combinations[key]
        found.append(Combination(key, c["verse"], c["text"], detail))

    for who, key in (("sun", "eye_right"), ("moon", "eye_right")):
        if house[who] == 2 and joined_or_aspected(who, ("mars", "saturn")):
            add(key, f"the {who.title()} is in the 2nd house with Mars or Saturn joined or aspecting")
    for who in ("sun", "moon"):
        if house[who] == 12 and joined_or_aspected(who, ("mars", "saturn")):
            add("eye_left", f"the {who.title()} is in the 12th house with Mars or Saturn joined or aspecting")
    third, eleventh = (lagna + 2) % 12, (lagna + 10) % 12

    def house_touched(s: int) -> bool:
        return any(sign[p] == s for p in ("mars", "saturn")) or bool(aspected_by(s, ("mars", "saturn")))
    if house_touched(third) and house_touched(eleventh) and joined_or_aspected("jupiter", ("mars", "saturn")):
        add("ear", "Mars or Saturn is in or aspects the 3rd house, the 11th house and Jupiter")
    if house["mars"] == 5 and any(lord[h] != "mars" and sign[lord[h]] == sign["mars"] for h in (6, 8)):
        add("stomach", "Mars is in the 5th house with the lord of the 6th or the 8th")
    for h, where in ((6, (7, 8)), (8, (7,))):
        lh = lord[h]
        if house[lh] in where and any(sign[m] == sign[lh] for m in MALEFICS if m != lh):
            add("private_parts" if lh == "venus" else "rectal", f"the lord of the {_ord(h)} ({lh.title()}) is in the {_ord(house[lh])} with a malefic")
    for p in BODIES:
        if house[p] not in (6, 8):
            continue
        where = _ord(house[p])
        keys = {"sun": "occupant_sun", "mars": "occupant_mars_ketu", "ketu": "occupant_mars_ketu", "venus": "occupant_venus",
                "jupiter": "occupant_jupiter", "saturn": "occupant_saturn"}
        if p in keys:
            add(keys[p], f"{p.title()} is in the {where} house")
        if p == "rahu" and "mars" in aspected_by(sign["rahu"], ("mars",)):
            add("rahu_mars", f"Rahu is in the {where} house, aspected by Mars")
        if p == "saturn" and sign["moon"] == sign["saturn"]:
            add("saturn_moon", f"Saturn and the Moon are together in the {where} house")
        if p == "moon" and (chart.planets["moon"].longitude - chart.planets["sun"].longitude) % 360.0 >= 180.0 \
                and sign["moon"] in WATERY and any(sign[m] == sign["moon"] for m in MALEFICS):
            add("waning_moon_water", f"the waning Moon is in the {where} house, in a watery sign, with a malefic")
    return Health(sources, overlaps, tuple(found))
