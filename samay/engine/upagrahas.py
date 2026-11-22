"""Phaladeepika chapter 25: the upagrahas (Gulika/Mandi, Yamakantaka, Ardhaprahara, Kala, Dhuma, Vyatipata, Paridhi, Indra Dhanus, Upaketu).

Gulika, Yamakantaka, Ardhaprahara and Kala are the lagna at a moment fixed by the book's ghatika tables from sunrise (day births) or sunset (night births);
the other five come from the Sun's longitude by the book's formulas. Texts are in data/rules/phaladeepika-ch25-upagrahas.yaml. Nothing is returned until a person
has checked that file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import daylight, house_effects
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch25-upagrahas.yaml"
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
TIMED = ("gulika", "yamakantaka", "ardhaprahara", "kala")
FROM_SUN = ("dhuma", "vyatipata", "paridhi", "indra_dhanus", "upaketu")
NAMES = {
    "gulika": "Gulika (Mandi)",
    "yamakantaka": "Yamakantaka",
    "ardhaprahara": "Ardhaprahara",
    "kala": "Kala",
    "dhuma": "Dhuma",
    "vyatipata": "Vyatipata",
    "paridhi": "Paridhi",
    "indra_dhanus": "Indra Dhanus",
    "upaketu": "Upaketu",
}
KENDRA_TRIKONA = {1, 4, 5, 7, 9, 10}


@dataclass(frozen=True)
class UpagrahaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    raw: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Point:
    key: str
    name: str
    longitude: float  # sidereal degrees
    sign: int
    house: int  # from the lagna


@dataclass(frozen=True)
class Upagrahas:
    points: tuple[Point, ...]
    when: str  # "day" or "night" or "" (no sunrise or sunset that day)
    effects: tuple[tuple[str, str, str], ...]  # (verse, heading, text)


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> UpagrahaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    g = raw["ghatikas"]
    for k in (
        "gulika_day",
        "gulika_night",
        "yamakantaka_day",
        "ardhaprahara_day",
        "kala_day",
    ):
        if len(g[k]) != 7 or not all(0 < x <= 30 for x in g[k]):
            raise ValueError(f"{path.name} ghatikas.{k}: seven values from 1 to 30")
    for table in ("gulika_house", "upaketu_house"):
        if set(raw[table]) - {"verse"} != set(range(1, 13)):
            raise ValueError(f"{path.name} {table}: needs all twelve houses")
    for table in ("gulika_with",):
        if set(raw[table]) - {"verse"} != set(BODIES):
            raise ValueError(f"{path.name} {table}: needs all nine planets")
    for k in ("nature", "dhuma_group", "strong_lord", "formulas"):
        if k not in raw:
            raise ValueError(f"{path.name}: missing {k}")
    return UpagrahaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw,
    )


def book_weekday(python_weekday: int) -> int:
    """Sunday-first index (0 = Sunday) from Python's Monday-first weekday."""
    return (python_weekday + 1) % 7


def moment_at(start: datetime, end: datetime, ghatika: float) -> datetime:
    """The moment `ghatika` of a 30-ghatika period that runs from start to end (the book's proportional scaling)."""
    return start + (end - start) * (ghatika / 30.0)


def from_sun(rules: UpagrahaRules, sun_longitude: float) -> dict[str, float]:
    """Dhuma, Vyatipata, Paridhi, Indra Dhanus and Upaketu from the Sun's sidereal longitude, by the book's formulas (25.5)."""
    f = rules.raw["formulas"]
    dhuma = (sun_longitude + f["dhuma_add"]) % 360.0
    vyatipata = (360.0 - dhuma) % 360.0
    paridhi = (vyatipata + 180.0) % 360.0
    indra = (360.0 - paridhi) % 360.0
    return {
        "dhuma": dhuma,
        "vyatipata": vyatipata,
        "paridhi": paridhi,
        "indra_dhanus": indra,
        "upaketu": (indra + f["upaketu_add"]) % 360.0,
    }


def timed_moments(
    rules: UpagrahaRules, local: datetime, latitude: float, longitude: float, tz: str
) -> tuple[str, dict[str, datetime]]:
    """("day" or "night", {key: moment}) for Gulika (always) and the other three (day births only; the book gives their night values nowhere).
    ("", {}) when the Sun does not both rise and set."""
    zone = ZoneInfo(tz)
    local = local.astimezone(zone)
    today = daylight.sun_times(latitude, longitude, tz, local.date())
    if today is None:
        return "", {}
    g = rules.raw["ghatikas"]
    if today.sunrise <= local < today.sunset:  # a day birth: the weekday of this sunrise
        d = book_weekday(local.date().weekday())
        out = {"gulika": moment_at(today.sunrise, today.sunset, g["gulika_day"][d])}
        for k in ("yamakantaka", "ardhaprahara", "kala"):
            out[k] = moment_at(today.sunrise, today.sunset, g[f"{k}_day"][d])
        return "day", out
    # a night birth: from the sunset of the weekday's day to the next sunrise (a birth before sunrise belongs to the day before)
    if local >= today.sunset:
        day, start = local.date(), today.sunset
        nxt = daylight.sun_times(latitude, longitude, tz, day + timedelta(days=1))
        end = nxt.sunrise if nxt else None
    else:
        day = local.date() - timedelta(days=1)
        prev = daylight.sun_times(latitude, longitude, tz, day)
        start, end = (prev.sunset if prev else None), today.sunrise
    if start is None or end is None:
        return "", {}
    d = book_weekday(day.weekday())
    return "night", {"gulika": moment_at(start, end, g["gulika_night"][d])}


def find(
    rules: UpagrahaRules,
    chart: Chart,
    local: datetime,
    latitude: float,
    longitude: float,
    tz: str,
    ascendant_at: Callable[[datetime], float],
) -> Upagrahas | None:
    """The upagrahas of this chart and what the book says of them. None until the rules are checked."""
    if not rules.servable:
        return None
    r = rules.raw
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
    when, moments = timed_moments(rules, local, latitude, longitude, tz)
    lon: dict[str, float] = {k: ascendant_at(m.astimezone(UTC)) for k, m in moments.items()}
    lon.update(from_sun(rules, chart.planets["sun"].longitude))
    points = tuple(
        Point(
            k,
            NAMES[k],
            lon[k],
            sign_index(lon[k]),
            house_from(lagna, sign_index(lon[k])),
        )
        for k in (*TIMED, *FROM_SUN)
        if k in lon
    )
    byk = {p.key: p for p in points}
    effects: list[tuple[str, str, str]] = [(r["nature"]["verse"], "In general", r["nature"]["general"])]
    g = byk.get("gulika")
    if g is not None:
        effects.append(
            (
                r["gulika_house"]["verse"],
                f"Gulika in the {g.house}th house",
                r["gulika_house"][g.house],
            )
        )
        for p in BODIES:
            if sign[p] == g.sign:
                effects.append(
                    (
                        r["gulika_with"]["verse"],
                        f"Gulika with {p.title()}",
                        r["gulika_with"][p],
                    )
                )
        lord = SIGN_LORDS[g.sign]
        ch20 = house_effects.load_rules()
        lh = house_from(lagna, sign[lord])
        stand = house_effects.strength(ch20, lord, sign[lord])
        if lh in KENDRA_TRIKONA or stand in (
            "own",
            "moolatrikona",
            "exaltation",
            "friendly",
        ):
            effects.append(
                (
                    r["strong_lord"]["verse"],
                    f"The lord of Gulika's house, {lord.title()}, is well placed",
                    r["strong_lord"]["text"],
                )
            )
    for k, key in (
        ("dhuma", "dhuma"),
        ("paridhi", "paridhi"),
        ("indra_dhanus", "indra_dhanus"),
        ("upaketu", "upaketu"),
        ("yamakantaka", "yamakantaka"),
    ):
        if k in byk:
            effects.append(
                (
                    r["dhuma_group"]["verse"],
                    f"{NAMES[k]} in the {byk[k].house}th house",
                    r["dhuma_group"][key],
                )
            )
    u = byk.get("upaketu")
    if u is not None:
        effects.append(
            (
                r["upaketu_house"]["verse"],
                f"Upaketu in the {u.house}th house",
                r["upaketu_house"][u.house],
            )
        )
    return Upagrahas(points, when, tuple(effects))
