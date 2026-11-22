"""Brihat Jataka chapter XII: the Nabhasa yogas, found from where the seven planets sit.

Texts and definitions come from data/rules/brihat-jataka-nabhasa.yaml. This module loads and validates it and decides which yogas a
chart has, by the precedence the text and its translator give. Nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-nabhasa.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
KENDRAS = (1, 4, 7, 10)
MOVABLE, FIXED, COMMON = (0, 3, 6, 9), (1, 4, 7, 10), (2, 5, 8, 11)
GROUPS = ("asraya", "dala", "akriti", "sankhya")


@dataclass(frozen=True)
class NabhasaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    yogas: dict[str, dict]
    akriti: dict[str, tuple[frozenset[int], ...]]
    vajra_yava: dict[str, dict]
    benefics: tuple[str, ...]
    malefics: tuple[str, ...]
    life_note: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Yoga:
    key: str
    name: str
    group: str
    verse: str
    text: str  # quoted; continues "A person born under a ... yoga"
    variant: str | None
    detail: str  # which houses or signs, computed from the chart


@dataclass(frozen=True)
class Nabhasa:
    yogas: tuple[Yoga, ...]
    checked: bool
    houses: tuple[int, ...]  # the houses (1-12) occupied by the seven planets
    sign_count: int
    life_note: str = ""
    life_except: str = ""
    life_verse: str = ""


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> NabhasaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    yogas = raw["yogas"]
    counts = {g: sum(1 for y in yogas.values() if y["group"] == g) for g in GROUPS}
    if counts != {"asraya": 3, "dala": 2, "akriti": 20, "sankhya": 7}:
        raise ValueError(
            f"{path.name}: the text counts 3 Asraya, 2 Dala, 20 Akriti and 7 Sankhya yogas, found {counts}"
        )
    for key, y in yogas.items():
        if not isinstance(y.get("text"), str) or not y["text"].strip() or not isinstance(y.get("verse"), str):
            raise ValueError(f"{path.name} {key}: needs a text and a verse")
    if sorted(y["signs"] for y in yogas.values() if y["group"] == "sankhya") != [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
    ]:
        raise ValueError(f"{path.name}: the Sankhya yogas run from 1 sign to 7")
    akriti = {}
    for key, shapes in raw["akriti"].items():
        if key not in yogas or yogas[key]["group"] != "akriti":
            raise ValueError(f"{path.name} akriti.{key}: not an Akriti yoga")
        for shape in shapes:
            if not shape or not all(1 <= h <= 12 for h in shape):
                raise ValueError(f"{path.name} akriti.{key}: houses must be 1-12")
        akriti[key] = tuple(frozenset(s) for s in shapes)
    if set(akriti) | set(raw["vajra_yava"]) != {k for k, y in yogas.items() if y["group"] == "akriti"}:
        raise ValueError(f"{path.name}: every Akriti yoga needs a definition")
    return NabhasaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        yogas,
        akriti,
        raw["vajra_yava"],
        tuple(raw["benefics"]),
        tuple(raw["malefics"]),
        raw["life_note"],
    )


def _benefic(chart: Chart, rules: NabhasaRules, planet: str) -> bool | None:
    if planet in rules.benefics:
        return True
    if planet in rules.malefics:
        return False
    return (
        chart.planets["moon"].longitude - chart.planets["sun"].longitude
    ) % 360.0 < 180.0  # the Moon: waxing = benefic


def find(rules: NabhasaRules, chart: Chart) -> Nabhasa:
    """The Nabhasa yogas of this chart. Empty until the rules are checked."""
    if not rules.servable:
        return Nabhasa((), False, (), 0)
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in SEVEN}
    house = {p: house_from(lagna, sign[p]) for p in SEVEN}
    occupied = frozenset(house.values())
    signs = frozenset(sign.values())
    found: list[Yoga] = []

    def add(key: str, detail: str) -> None:
        y = rules.yogas[key]
        found.append(
            Yoga(
                key,
                y["name"],
                y["group"],
                y["verse"],
                y["text"].strip(),
                y.get("variant"),
                detail,
            )
        )

    in_houses = f"the planets are in the {', '.join(_ord(h) for h in sorted(occupied))} house"
    # Akriti: the planets occupy exactly the named houses; Vajra and Yava first (they are the more specific shape).
    akriti = None
    for key, shape in rules.vajra_yava.items():
        wanted = set(shape["benefic_houses"]) | set(shape["malefic_houses"])
        if occupied == wanted and all(
            bool(_benefic(chart, rules, p)) == (house[p] in shape["benefic_houses"]) for p in SEVEN
        ):
            akriti = key
    if akriti is None:
        akriti = next(
            (k for k, shapes in rules.akriti.items() if any(occupied == s for s in shapes)),
            None,
        )
    if akriti is not None:
        add(akriti, in_houses)

    # Dala: three benefics in three kendras and no malefic in any kendra, or the reverse
    kend = {p: house[p] for p in SEVEN if house[p] in KENDRAS}
    ben = [p for p in rules.benefics if p in kend]
    mal = [p for p in rules.malefics if p in kend]
    dala = None
    if len({kend[p] for p in ben}) == 3 and not mal:
        dala = "srik"
        add(
            "srik",
            f"{', '.join(p.title() for p in ben)} in three kendras and no malefic in a kendra",
        )
    elif len({kend[p] for p in mal}) == 3 and not ben:
        dala = "sarpa"
        add(
            "sarpa",
            f"{', '.join(p.title() for p in mal)} in three kendras and no benefic in a kendra",
        )

    n = len(signs)
    if akriti is None:
        kind = (("rajju", MOVABLE), ("musala", FIXED), ("nala", COMMON))
        asraya = next((k for k, group in kind if signs <= set(group)), None)
        if asraya and n >= 2:  # one sign is Gola (the commentator), not an Asraya
            add(
                asraya,
                f"all the planets are in {'movable' if asraya == 'rajju' else 'fixed' if asraya == 'musala' else 'common'} signs",
            )
        elif not (
            dala and n >= 4
        ):  # a Dala that is also Vallaki, Damini, Pasa or Kedara counts as the Dala only
            key = next(k for k, y in rules.yogas.items() if y["group"] == "sankhya" and y["signs"] == n)
            add(key, f"the planets are in {n} sign{'s' if n > 1 else ''}")
    n_houses = tuple(sorted(occupied))
    return Nabhasa(
        tuple(found),
        True,
        n_houses,
        n,
        rules.life_note["text"],
        rules.life_note["except"],
        rules.life_note["verse"],
    )


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
