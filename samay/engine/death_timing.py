"""Phaladeepika's death-timing rules (13.18-19, 20.32, 20.40): the stretches of days in which each of the book's conditions holds.

The book gives conditions, never dates, and this module never gives one: it returns windows over a few years and says so. Nothing is returned until a
person has checked data/rules/phaladeepika-death-timing.yaml. Sensitive: the bot shows it only after its own warning and a tap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from . import house_effects
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .house_timing import DashaWindow, RuleWindows, _dasha_flags, _result, _trines
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, Period, house_from, navamsa_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-death-timing.yaml"
IDS = (
    "saturn_point",
    "lagna_lord_transit",
    "jupiter_eighth",
    "maraka_dasha",
    "eighth_twelfth_antardasha",
)
MALEFICS = ("sun", "mars", "saturn", "rahu", "ketu")
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")


@dataclass(frozen=True)
class DeathRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    rules: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class DeathTiming:
    start: datetime
    end: datetime
    results: tuple[RuleWindows, ...]
    dashas: tuple[
        DashaWindow, ...
    ]  # the periods of rules maraka_dasha / eighth_twelfth_antardasha
    maraka: tuple[str, ...]
    weak_lords: tuple[str, ...]
    tz: str = "UTC"


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> DeathRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rules = {r["id"]: r for r in raw["rules"]}
    if set(rules) != set(IDS):
        raise ValueError(f"{path.name}: rules must be exactly {IDS}")
    for r in rules.values():
        if not all(
            isinstance(r.get(f), str) and r[f].strip()
            for f in ("verse", "definition", "text")
        ):
            raise ValueError(f"{path.name} {r['id']}: needs verse, definition and text")
    return DeathRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        rules,
    )


def find(
    rules: DeathRules,
    chart: Chart,
    dashas: tuple[Period, ...],
    times: list[datetime],
    track: dict[str, list[float]],
) -> DeathTiming | None:
    """The stretches of `times` (one per day) in which each rule holds. None until the rules are checked."""
    if not rules.servable:
        return None
    ch20 = house_effects.load_rules()
    n = len(times)
    signs = {p: [sign_index(x) for x in track[p]] for p in track}
    nat = {p: sign_index(chart.planets[p].longitude) for p in chart.planets}
    lagna = sign_index(chart.ascendant)
    house = {p: house_from(lagna, s) for p, s in nat.items()}
    lord = {h: SIGN_LORDS[(lagna + h - 1) % 12] for h in range(1, 13)}

    def stand(p: str) -> str:
        return house_effects.strength(ch20, p, nat[p])

    out: list[RuleWindows] = []
    total = (
        sum(chart.planets[p].longitude for p in ("sun", "moon", "jupiter", "saturn"))
        % 360.0
    )
    point = sign_index(total)
    out.append(
        _result(
            rules.rules["saturn_point"],
            "birth",
            0,
            [signs["saturn"][i] == point for i in range(n)],
            times,
            f"the sum of the four longitudes falls in the sign {point + 1} (counted from Aries); the book applies this only to a native of short life, which the bot cannot tell",
        )
    )
    ll = lord[1]
    afflicted = [
        w
        for w, ok in (
            (
                "joined with a malefic",
                any(q != ll and nat[q] == nat[ll] for q in MALEFICS),
            ),
            ("combust", house_effects.is_astangata(ch20, ll, chart)),
            ("in its debilitation sign", stand(ll) == "depression"),
            ("in an enemy's sign", stand(ll) == "inimical"),
        )
        if ok
    ]
    if afflicted:
        flags = []
        for i in range(n):
            s = signs[ll][i]
            flags.append(
                house_from(lagna, s) in (1, 6, 8, 12)
                or house_from(nat["moon"], s) in (1, 6, 8, 12)
            )
        out.append(
            _result(
                rules.rules["lagna_lord_transit"],
                "lagna and Moon sign",
                1,
                flags,
                times,
                f"the lagna lord {ll.title()} is {', '.join(afflicted)} at birth",
            )
        )
    else:
        out.append(
            _result(
                rules.rules["lagna_lord_transit"],
                "lagna and Moon sign",
                1,
                [False] * n,
                times,
                f"does not apply: the lagna lord {ll.title()} is not joined with a malefic, combust, debilitated or in an enemy's sign",
            )
        )
    l8 = lord[8]
    targets = _trines(nat[l8]) | _trines(navamsa_sign(chart.planets[l8].longitude))
    out.append(
        _result(
            rules.rules["jupiter_eighth"],
            "lagna",
            8,
            [signs["jupiter"][i] in targets for i in range(n)],
            times,
        )
    )
    maraka = sorted({lord[2], lord[7]} | {p for p in nat if house[p] in (2, 7)})
    maraka = [
        p
        for p in maraka
        if p in SEVEN and stand(p) in ("own", "moolatrikona", "exaltation")
    ]
    flags_m, shown_m = (
        _dasha_flags(dashas, times, set(maraka)) if maraka else ([False] * n, [])
    )
    out.append(
        _result(
            rules.rules["maraka_dasha"],
            "lagna",
            2,
            flags_m,
            times,
            (
                ""
                if maraka
                else "no lord of, or planet in, the 2nd or 7th is powerful (own, moolatrikona or exaltation sign) at birth"
            ),
        )
    )
    weak = sorted(
        {
            p
            for p in (lord[8], lord[12])
            if stand(p) == "depression" or house_effects.is_astangata(ch20, p, chart)
        }
    )
    flags_w = [False] * n
    shown_w: list[DashaWindow] = []
    if weak:
        _, shown_all = _dasha_flags(dashas, times, set(weak))
        shown_w = [d for d in shown_all if d.kind == "antardasha"]
        flags_w = [any(d.start <= t < d.end for d in shown_w) for t in times]
    out.append(
        _result(
            rules.rules["eighth_twelfth_antardasha"],
            "lagna",
            8,
            flags_w,
            times,
            (
                ""
                if weak
                else "neither the 8th nor the 12th lord is very weak (debilitated or combust) at birth"
            ),
        )
    )
    return DeathTiming(
        times[0],
        times[-1],
        tuple(out),
        tuple(sorted([*shown_m, *shown_w], key=lambda d: (d.start, d.kind))),
        tuple(maraka),
        tuple(weak),
    )
