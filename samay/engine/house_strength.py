"""Phaladeepika chapter 15: whether each house of the chart is helped or harmed.

Texts come from data/rules/phaladeepika-ch15-house-strength.yaml (paraphrased); the conditions are coded here. Nothing is returned until a person has
checked the file. The book reads a house by its occupants, its lord and the aspects on it, and says a house is not good or bad by itself.
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
from .vedic import SIGN_LORDS, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch15-house-strength.yaml"
BODIES = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
SEVEN = BODIES[:7]
MALEFICS = ("sun", "mars", "saturn", "rahu", "ketu")
BENEFICS = ("mercury", "jupiter", "venus")
DUSTHANA = (6, 8, 12)
FULL_ASPECTS = {"mars": (4, 7, 8), "jupiter": (5, 7, 9), "saturn": (3, 7, 10)}
RULE_KEYS = ("helped_by_occupants", "harmed_by_occupants", "destroyed_lord", "destroyed_occupant", "malefic_in_dusthana", "lord_in_dusthana",
             "saved_by_benefic", "lagna_lord_in_it", "lagna_lord_with_lord", "lagna_lord_owns_dusthana", "occupied_benefic", "occupied_malefic",
             "dusthana_malefic", "dusthana_benefic")


@dataclass(frozen=True)
class StrengthRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    mixed: str
    rules: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Finding:
    key: str
    verse: str
    text: str
    detail: str
    kind: str  # "helps", "harms" or "note"


@dataclass(frozen=True)
class HouseReading:
    house: int
    sign: int
    lord: str
    findings: tuple[Finding, ...]
    mixed: bool  # both helping and harming findings (the book calls this mixed)


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> StrengthRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["rules"]) != set(RULE_KEYS):
        raise ValueError(f"{path.name}: rules must be exactly {RULE_KEYS}")
    for k, r in raw["rules"].items():
        if not all(isinstance(r.get(f), str) and r[f].strip() for f in ("verse", "definition", "text")):
            raise ValueError(f"{path.name} {k}: needs verse, definition and text")
    return StrengthRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")),
                         raw["frame"], raw["mixed"], raw["rules"])


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def find(rules: StrengthRules, chart: Chart) -> tuple[HouseReading, ...] | None:
    """A reading of each of the twelve houses by the chapter's tests. None until the rules are checked."""
    if not rules.servable:
        return None
    ch20 = house_effects.load_rules()
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
    house = {p: house_from(lagna, s) for p, s in sign.items()}
    lord = {h: SIGN_LORDS[(lagna + h - 1) % 12] for h in range(1, 13)}
    waxing = (chart.planets["moon"].longitude - chart.planets["sun"].longitude) % 360.0 < 180.0
    benefics = BENEFICS + (("moon",) if waxing else ())

    def stand(p: str) -> str:
        return house_effects.strength(ch20, p, sign[p])

    def sees(by: str, target: int) -> bool:
        return by in SEVEN and sign[by] != target and house_from(sign[by], target) in FULL_ASPECTS.get(by, (7,))

    def helped(p: str) -> bool:
        return any(q != p and (sign[q] == sign[p] or sees(q, sign[p])) for q in BENEFICS)

    def afflicted(p: str) -> bool:
        return p in SEVEN and (stand(p) in ("depression", "inimical") or house_effects.is_astangata(ch20, p, chart))

    out = []
    for h in range(1, 13):
        hs = (lagna + h - 1) % 12
        lh = lord[h]
        found: list[Finding] = []

        def add(key: str, detail: str, kind: str, into: list[Finding] = found) -> None:
            r = rules.rules[key]
            into.append(Finding(key, r["verse"], r["text"], detail, kind))

        around = [(h + d - 1 - 1) % 12 + 1 for d in (1, 2, 4, 5, 7, 9, 10)]
        ben_hit = [x for x in around if any(house[p] == x for p in benefics)]
        mal_hit = [x for x in around if any(house[p] == x for p in MALEFICS)]
        if len(ben_hit) >= 3 and not mal_hit:
            add("helped_by_occupants", f"benefics hold {len(ben_hit)} of those houses ({', '.join(_ord(x) for x in ben_hit)} from it) and no malefic does", "helps")
        if len(mal_hit) >= 3 and not ben_hit:
            add("harmed_by_occupants", f"malefics hold {len(mal_hit)} of those houses ({', '.join(_ord(x) for x in mal_hit)} from it) and no benefic does", "harms")
        reasons = []
        if house[lh] == 8:
            reasons.append("in the 8th house")
        if stand(lh) == "depression":
            reasons.append("in its sign of debilitation")
        if stand(lh) == "inimical":
            reasons.append("in an enemy's sign")
        if house_effects.is_astangata(ch20, lh, chart):
            reasons.append("combust")
        if reasons and not helped(lh):
            add("destroyed_lord", f"the lord {lh.title()} is {', '.join(reasons)} with no benefic joined or aspecting", "harms")
        for p in BODIES:
            if house[p] == h and afflicted(p) and not helped(p):
                add("destroyed_occupant", f"{p.title()} is in the house, {stand(p) if stand(p) in ('depression', 'inimical') else 'combust'}, with no benefic joined or aspecting", "harms")
        for d in (6, 8, 12):
            x = (h + d - 1 - 1) % 12 + 1
            bad = [p for p in MALEFICS if house[p] == x]
            if bad:
                add("malefic_in_dusthana", f"{', '.join(p.title() for p in bad)} in the {_ord(d)} from it", "harms")
        if house[lh] in DUSTHANA:
            add("lord_in_dusthana", f"the lord {lh.title()} is in the {_ord(house[lh])} house", "harms")
        for d in DUSTHANA:
            if lord[d] != lh and house[lord[d]] == h:
                add("lord_in_dusthana", f"{lord[d].title()}, lord of the {_ord(d)}, is in the house", "harms")
        saver = [p for p in BENEFICS if house[p] == h or sees(p, hs)]
        if saver and any(f.kind == "harms" for f in found):
            add("saved_by_benefic", f"{', '.join(p.title() for p in saver)} sits in it or aspects it", "helps")
        if h not in DUSTHANA:
            ben = [p for p in BENEFICS if house[p] == h]
            mal = [p for p in MALEFICS if house[p] == h]
            if ben:
                add("occupied_benefic", f"{', '.join(p.title() for p in ben)} in it", "helps")
            if mal:
                add("occupied_malefic", f"{', '.join(p.title() for p in mal)} in it", "harms")
        else:
            ben = [p for p in BENEFICS if house[p] == h]
            mal = [p for p in MALEFICS if house[p] == h]
            if mal:
                add("dusthana_malefic", f"{', '.join(p.title() for p in mal)} in it", "harms")
            if ben:
                add("dusthana_benefic", f"{', '.join(p.title() for p in ben)} in it", "note")
        if lord[1] != lh and house[lord[1]] == h:
            add("lagna_lord_in_it", f"the lagna lord {lord[1].title()} is in the house", "helps")
        if lord[1] != lh and (sign[lord[1]] == sign[lh] or sees(lord[1], sign[lh]) or sees(lh, sign[lord[1]])):
            add("lagna_lord_with_lord", f"the lord {lh.title()} is joined with or aspected by the lagna lord {lord[1].title()}", "helps")
        if h == 1 and any(lord[d] == lord[1] for d in DUSTHANA):
            add("lagna_lord_owns_dusthana", f"{lord[1].title()} rules the lagna and also the {', '.join(_ord(d) for d in DUSTHANA if lord[d] == lord[1])}", "note")
        mixed = any(f.kind == "helps" for f in found) and any(f.kind == "harms" for f in found)
        out.append(HouseReading(h, hs, lh, tuple(found), mixed))
    return tuple(out)
