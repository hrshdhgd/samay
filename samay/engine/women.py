"""Phaladeepika chapter 11: the book's pointers for a woman's chart about her husband, marriage and children.

Texts come from data/rules/phaladeepika-ch11-women.yaml (paraphrased). Conditions are coded here. Sensitive: the bot shows it only after a warning and a
tap. The verses about a woman's chastity and character (11.4, 11.6-8) are not built. Nothing is returned until a person has checked the file.
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

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch11-women.yaml"
BODIES = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
    "rahu",
    "ketu",
)
MALEFICS = ("sun", "mars", "saturn", "rahu", "ketu")
BENEFICS = ("mercury", "jupiter", "venus")
FULL_ASPECTS = {"mars": (4, 7, 8), "jupiter": (5, 7, 9), "saturn": (3, 7, 10)}
RULE_KEYS = (
    "even_signs_benefic",
    "odd_signs_malefic",
    "seventh_lord_benefic",
    "seventh_lord_not_benefic",
    "mars_in_seventh",
    "mixed_seventh",
    "malefic_eighth",
    "malefic_second",
    "benefics_trikonas",
    "malefics_trikonas",
    "five_malefic_moon",
)


@dataclass(frozen=True)
class WomenRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    houses: dict
    rules: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Pointer:
    key: str
    verse: str
    text: str
    detail: str


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> WomenRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["rules"]) != set(RULE_KEYS):
        raise ValueError(f"{path.name}: rules must be exactly {RULE_KEYS}")
    for k, r in raw["rules"].items():
        if not all(
            isinstance(r.get(f), str) and r[f].strip()
            for f in ("verse", "definition", "text")
        ):
            raise ValueError(f"{path.name} {k}: needs verse, definition and text")
    return WomenRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw["houses"],
        raw["rules"],
    )


def find(rules: WomenRules, chart: Chart) -> tuple[Pointer, ...] | None:
    """The book's pointers about husband, marriage and children that this chart meets. None until the rules are checked."""
    if not rules.servable:
        return None
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
    house = {p: house_from(lagna, s) for p, s in sign.items()}

    def sees(by: str, target: int) -> bool:
        return (
            by in ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
            and sign[by] != target
            and house_from(sign[by], target) in FULL_ASPECTS.get(by, (7,))
        )

    found: list[Pointer] = []

    def add(key: str, detail: str) -> None:
        r = rules.rules[key]
        found.append(Pointer(key, r["verse"], r["text"], detail))

    even = lambda s: s % 2 == 1  # Taurus, Cancer, ... are the even signs
    moon = sign["moon"]
    if even(lagna) and even(moon):
        ben = [b for b in BENEFICS if sees(b, lagna) and sees(b, moon)]
        if ben:
            add(
                "even_signs_benefic",
                f"the lagna and the Moon are in even signs and {', '.join(b.title() for b in ben)} aspects both",
            )
    if not even(lagna) and not even(moon):
        mal = [m for m in ("sun", "mars", "saturn") if sees(m, lagna) and sees(m, moon)]
        if mal:
            add(
                "odd_signs_malefic",
                f"the lagna and the Moon are in odd signs and {', '.join(m.title() for m in mal)} aspects both",
            )
    lord7 = SIGN_LORDS[(lagna + 6) % 12]
    add(
        "seventh_lord_benefic" if lord7 in BENEFICS else "seventh_lord_not_benefic",
        f"the 7th house is owned by {lord7.title()}",
    )
    seventh = [p for p in BODIES if house[p] == 7]
    if "mars" in seventh:
        add("mars_in_seventh", "Mars is in the 7th house")
    if any(p in BENEFICS for p in seventh) and any(p in MALEFICS for p in seventh):
        add(
            "mixed_seventh",
            f"{', '.join(p.title() for p in seventh)} are in the 7th house",
        )
    for h, key in ((8, "malefic_eighth"), (2, "malefic_second")):
        mal = [p for p in MALEFICS if house[p] == h]
        if mal:
            add(
                key,
                (
                    f"{', '.join(p.title() for p in mal)} in the {h}th house"
                    if h != 2
                    else f"{', '.join(p.title() for p in mal)} in the 2nd house"
                ),
            )
    tri = [p for p in BODIES if house[p] in (1, 5, 9)]
    ben_t, mal_t = [p for p in tri if p in BENEFICS], [p for p in tri if p in MALEFICS]
    if ben_t and not mal_t:
        add(
            "benefics_trikonas",
            f"{', '.join(p.title() for p in ben_t)} in the 1st, 5th or 9th, no malefic there",
        )
    if mal_t and not ben_t:
        add(
            "malefics_trikonas",
            f"{', '.join(p.title() for p in mal_t)} in the 1st, 5th or 9th, no benefic there",
        )
    if moon in (1, 4, 5, 7) and house["moon"] == 5:
        add(
            "five_malefic_moon",
            "the Moon is in Taurus, Leo, Virgo or Scorpio, and that sign is the 5th house",
        )
    return tuple(found)
