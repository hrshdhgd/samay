"""Phaladeepika chapter 26: the results of the planets' transits (gochara), counted from the natal Moon sign.

Everything the text says comes from data/rules/phaladeepika-ch26-gochara.yaml. This module only works out where each
planet goes during a period (its "stays" in signs), which house from the Moon each stay is, and whether another planet
obstructs a good result (vedha). Effects are returned only once the rules file has been checked by a person.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .paths import DATA_DIR
from .vedic import house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch26-gochara.yaml"
GRAHAS = (
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
SEVEN = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
)  # the planets that can obstruct (vedha)


@dataclass(frozen=True)
class Vedha:
    pairs: dict[int, int]  # good house -> the house that obstructs it
    exempt: frozenset[str]
    verse: int


@dataclass(frozen=True)
class GocharaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    favourable: dict[str, frozenset[int]]
    vedha: dict[str, Vedha]
    effects: dict[str, dict[int, str]]
    verses: dict[str, str]
    hidden: frozenset[tuple[str, int]]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


def _houses(values, where: str) -> list[int]:
    out = [int(h) for h in values]
    if any(not 1 <= h <= 12 for h in out):
        raise ValueError(f"{where}: houses must be 1-12")
    return out


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> GocharaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    for section in ("favourable", "vedha", "effects"):
        unknown = set(raw[section]) - set(GRAHAS)
        if unknown:
            raise ValueError(f"{path.name} {section}: unknown planet(s) {sorted(unknown)}")
    effects, verses, hidden = {}, {}, set()
    for planet, block in raw["effects"].items():
        houses = {}
        for h, row in block["houses"].items():
            text = row["text"] if isinstance(row, dict) else row
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{path.name} effects.{planet}.{h}: needs a text")
            houses[_houses([h], f"effects.{planet}")[0]] = text.strip()
            if isinstance(row, dict) and row.get("hidden"):
                hidden.add((planet, int(h)))
        if set(houses) != set(range(1, 13)):
            raise ValueError(f"{path.name} effects.{planet}: needs all twelve houses")
        effects[planet], verses[planet] = houses, str(block["verse"])
    vedha = {}
    for planet, block in raw["vedha"].items():
        pairs = {int(k): int(x) for k, x in block["pairs"].items()}
        _houses([*pairs, *pairs.values()], f"vedha.{planet}")
        if any(k == x for k, x in pairs.items()):
            raise ValueError(f"{path.name} vedha.{planet}: a house cannot obstruct itself")
        if not set(pairs) <= set(raw["favourable"][planet]):
            raise ValueError(f"{path.name} vedha.{planet}: vedha is only for the favourable houses")
        vedha[planet] = Vedha(pairs, frozenset(block.get("exempt", [])), int(block["verse"]))
    return GocharaRules(
        level=v.get("level", "unchecked"),
        checked_by=v.get("checked_by"),
        edition=raw["edition"],
        pages=str(raw.get("pages", "")),
        favourable={p: frozenset(_houses(hs, f"favourable.{p}")) for p, hs in raw["favourable"].items()},
        vedha=vedha,
        effects=effects,
        verses=verses,
        hidden=frozenset(hidden),
    )


@dataclass(frozen=True)
class Stay:
    """One planet in one sign during the period. `start` is None when it was already there when the period began,
    `end` is None when it is still there when the period ends (the dates are to the sampling step).
    """

    planet: str
    sign: int
    house: int  # counted from the natal Moon sign
    start: datetime | None
    end: datetime | None
    favourable: bool | None = None  # None: the text gives no result for this planet (Ketu)
    effect: str | None = None  # only from a checked rules file
    verse: str | None = None
    vedha_house: int | None = None  # the house that obstructs this good result, when the text names one
    blocked_by: tuple[
        str, ...
    ] = ()  # planets in the vedha house at the middle of the stay (within the period)
    points: int | None = None  # the planet's own ashtakavarga points in this sign (Sun to Saturn only)


def stays(
    times: list[datetime],
    track: dict[str, list[float]],
    moon_sign: int,
    planets: tuple[str, ...],
    rules: GocharaRules | None = None,
    check_vedha: bool = True,
    points: dict[str, list[int]] | None = None,
) -> list[Stay]:
    """Each planet's stays in signs over the sampled moments, in time order per planet, with the text's reading."""
    out = []
    n = len(times)
    for planet in planets:
        signs = [sign_index(x) for x in track[planet]]
        begin = 0
        for i in range(1, n + 1):
            if i < n and signs[i] == signs[begin]:
                continue
            sign = signs[begin]
            house = house_from(moon_sign, sign)
            stay = Stay(
                planet,
                sign,
                house,
                times[begin] if begin > 0 else None,
                times[i] if i < n else None,
            )
            stay = _read(stay, rules, track, moon_sign, (begin + i - 1) // 2, check_vedha)
            if points and planet in points:
                stay = replace(stay, points=points[planet][sign])
            out.append(stay)
            begin = i
    return out


def _read(
    stay: Stay,
    rules: GocharaRules | None,
    track,
    moon_sign: int,
    mid: int,
    check_vedha: bool,
) -> Stay:
    if rules is None or stay.planet not in rules.favourable:
        return stay
    good = stay.house in rules.favourable[stay.planet]
    effect = verse = None
    if rules.servable and (stay.planet, stay.house) not in rules.hidden:
        effect, verse = (
            rules.effects[stay.planet][stay.house],
            rules.verses[stay.planet],
        )
    vedha_house, blocked = None, ()
    v = rules.vedha.get(stay.planet)
    if good and v and stay.house in v.pairs:
        vedha_house = v.pairs[stay.house]
        if check_vedha:
            blocked = tuple(
                g
                for g in SEVEN
                if g != stay.planet
                and g not in v.exempt
                and house_from(moon_sign, sign_index(track[g][mid])) == vedha_house
            )
    return Stay(
        stay.planet,
        stay.sign,
        stay.house,
        stay.start,
        stay.end,
        good,
        effect,
        verse,
        vedha_house,
        blocked,
    )
