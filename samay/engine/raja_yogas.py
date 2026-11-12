"""Brihat Jataka chapter XI: the raja yogas whose configurations are stated plainly enough to decide from a chart.

Texts and configurations come from data/rules/brihat-jataka-raja-yogas.yaml. This module loads and validates it and checks a chart
against each; nothing is returned until a person has checked the file.
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

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-raja-yogas.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
_SIGN = {name: i for i, name in enumerate(SIGNS)}


@dataclass(frozen=True)
class RajaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    configs: tuple[dict, ...]
    exalted: dict
    strong: dict
    family: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    id: str
    verse: str
    text: str  # quoted
    detail: str
    family_note: str


def _item_ok(item: dict, where: str) -> None:
    if item["planet"] not in SEVEN:
        raise ValueError(f"{where}: unknown planet {item['planet']!r}")
    given = [k for k in ("sign", "signs", "house", "houses") if k in item]
    if len(given) != 1:
        raise ValueError(f"{where}: needs exactly one of sign / signs / house / houses")
    for s in ([item["sign"]] if "sign" in item else item.get("signs", [])):
        if s not in _SIGN:
            raise ValueError(f"{where}: unknown sign {s!r}")
    for h in ([item["house"]] if "house" in item else item.get("houses", [])):
        if not 1 <= h <= 12:
            raise ValueError(f"{where}: house must be 1-12")


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> RajaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    seen = set()
    for c in raw["configs"]:
        where = f"{path.name} {c.get('id')}"
        if c["id"] in seen or not c.get("text") or c.get("result") not in ("royal", "royal_only") or not c.get("all"):
            raise ValueError(f"{where}: needs a unique id, text, result (royal / royal_only) and conditions")
        seen.add(c["id"])
        for item in c["all"]:
            _item_ok(item, where)
        for s in c.get("lagna", []):
            if s not in _SIGN:
                raise ValueError(f"{where}: unknown lagna sign {s!r}")
    return RajaRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")),
                     tuple(raw["configs"]), raw["exalted"], raw["strong_planets"], raw["family_notes"])


def _holds(item: dict, sign: dict[str, int], house: dict[str, int], chart: Chart) -> bool:
    p = item["planet"]
    if "house" in item or "houses" in item:
        return house[p] in ([item["house"]] if "house" in item else item["houses"])
    wanted = {_SIGN[s] for s in ([item["sign"]] if "sign" in item else item["signs"])}
    if sign[p] not in wanted:
        return False
    return not item.get("first_half") or degree_in_sign(chart.planets[p].longitude) < 15.0


def find(rules: RajaRules, chart: Chart) -> tuple[Found, ...]:
    """The raja yogas this chart has. Empty until the rules are checked."""
    if not rules.servable:
        return ()
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in SEVEN}
    house = {p: house_from(lagna, s) for p, s in sign.items()}
    out = []
    for c in rules.configs:
        if c.get("lagna") and SIGNS[lagna] not in c["lagna"]:
            continue
        if all(_holds(item, sign, house, chart) for item in c["all"]):
            note = rules.family["anyone"] if c["result"] == "royal" else rules.family["royal_only"]
            out.append(Found(c["id"], c["verse"], c["text"], f"the rising sign is {SIGNS[lagna]} and the planets stand as the verse says", note))
    # verse 1: three or more planets in their exaltation signs
    ch20 = house_effects.load_rules()
    exalted = [p for p in SEVEN if house_effects.strength(ch20, p, sign[p]) == "exaltation"]
    if len(exalted) >= 3:
        mal = [p for p in exalted if p in rules.exalted["malefics"]]
        ben = [p for p in exalted if p in rules.exalted["benefics"]]
        key = "malefic" if not ben else "benefic" if not mal else "mixed"
        out.append(Found("v1", rules.exalted["verse"], rules.exalted[key],
                         f"{', '.join(p.title() for p in exalted)} are in their exaltation signs", ""))
    # verse 13: three or more planets in their own, exaltation or moolatrikona signs
    own = [p for p in SEVEN if house_effects.strength(ch20, p, sign[p]) in ("own", "moolatrikona", "exaltation")]
    if len(own) >= 3:
        text = rules.strong["five"] if len(own) >= 5 else rules.strong["three"]
        out.append(Found("v13", rules.strong["verse"], text,
                         f"{len(own)} planets are in their own, exaltation or moolatrikona signs: {', '.join(p.title() for p in own)} "
                         "(the text says 'powerful' as well; strength is not measured)", ""))
    return tuple(out)
