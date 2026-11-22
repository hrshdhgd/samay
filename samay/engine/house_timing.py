"""Phaladeepika's timing rules: when a house bears fruit (chapter 16, verses 31-35) and when marriage is likely (chapter 10, verses 12-14).

The statements come from data/rules/phaladeepika-timing.yaml. This module codes the conditions, finds the stretches of a period (one day at a
time) in which each holds for a chart, and merges them into windows. The text gives conditions, never dates; nothing is returned until a person
has checked the file.
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
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, Period, antardashas, house_from, navamsa_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-timing.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
FULL_ASPECTS = {
    "mars": (4, 7, 8),
    "jupiter": (5, 7, 9),
    "saturn": (3, 7, 10),
}  # Brihat Jataka II.13; every other body the 7th
GENERAL_IDS = ("t1", "t2", "t3", "t4", "jupiter", "conjunction")
MARRIAGE_IDS = ("m1", "m2", "m3")
STANDING_RANK = {
    "exaltation": 6,
    "moolatrikona": 5,
    "own": 4,
    "friendly": 3,
    "neutral": 2,
    "inimical": 1,
    "depression": 0,
}


@dataclass(frozen=True)
class TimingRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    moon_note: str
    general: dict[str, dict]
    marriage: dict[str, dict]
    areas: dict[str, tuple[int, ...]]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class RuleWindows:
    id: str
    verse: str
    text: str
    ref: str  # "lagna" or "the Moon sign"
    house: int
    windows: tuple[tuple[datetime, datetime], ...]  # first and last day (UTC) of each stretch
    days: int  # days on which the condition holds
    total: int  # days in the period
    note: str = ""  # a caveat computed for this chart


@dataclass(frozen=True)
class DashaWindow:
    kind: str  # "mahadasha" or "antardasha"
    lord: str
    maha: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Timing:
    area: str
    houses: tuple[int, ...]
    start: datetime
    end: datetime
    general: tuple[RuleWindows, ...]
    marriage: tuple[RuleWindows, ...]
    dashas: tuple[DashaWindow, ...]  # periods of the planets of rule m2
    m2_planets: tuple[str, ...]
    m3_planets: tuple[str, ...]
    tz: str = "UTC"


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> TimingRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    general = {r["id"]: r for r in raw["general"]}
    marriage = {r["id"]: r for r in raw["marriage"]["rules"]}
    if (
        set(general) != set(GENERAL_IDS)
        or set(marriage) != set(MARRIAGE_IDS)
        or raw["marriage"]["house"] != 7
    ):
        raise ValueError(
            f"{path.name}: needs rules {GENERAL_IDS} and, for marriage (the 7th house), {MARRIAGE_IDS}"
        )
    for r in (*general.values(), *marriage.values()):
        if not all(isinstance(r.get(f), str) and r[f].strip() for f in ("verse", "definition", "text")):
            raise ValueError(f"{path.name} {r.get('id')}: needs verse, definition and text")
    areas = {a: tuple(hs) for a, hs in raw["areas"].items()}
    if not all(1 <= h <= 12 for hs in areas.values() for h in hs):
        raise ValueError(f"{path.name}: houses must be 1-12")
    return TimingRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw["moon_note"],
        general,
        marriage,
        areas,
    )


def _trines(sign: int) -> set[int]:
    return {sign, (sign + 4) % 12, (sign + 8) % 12}


def _aspects(by: str, by_sign: int, target_sign: int) -> bool:
    return house_from(by_sign, target_sign) in FULL_ASPECTS.get(by, (7,))


def _windows(flags: list[bool], times: list[datetime]) -> tuple[tuple[datetime, datetime], ...]:
    out, begin = [], None
    for i, on in enumerate(flags):
        if on and begin is None:
            begin = i
        if begin is not None and (not on or i == len(flags) - 1):
            last = i if on else i - 1
            out.append((times[begin], times[last]))
            begin = None
    return tuple(out)


def _result(
    rule: dict,
    ref: str,
    house: int,
    flags: list[bool],
    times: list[datetime],
    note: str = "",
) -> RuleWindows:
    return RuleWindows(
        rule["id"],
        rule["verse"],
        rule["text"],
        ref,
        house,
        _windows(flags, times),
        sum(flags),
        len(flags),
        note,
    )


def _dasha_flags(
    dashas: tuple[Period, ...], times: list[datetime], lords: set[str]
) -> tuple[list[bool], list[DashaWindow]]:
    """A flag per day for 'a mahadasha or antardasha of one of these planets runs', and those periods clipped to the timeline."""
    spans = []
    for maha in dashas:
        if maha.lord in lords:
            spans.append(DashaWindow("mahadasha", maha.lord, maha.lord, maha.start, maha.end))
        spans += [
            DashaWindow("antardasha", a.lord, maha.lord, a.start, a.end)
            for a in antardashas(maha)
            if a.lord in lords
        ]
    flags = [any(s.start <= t < s.end for s in spans) for t in times]
    shown = [s for s in spans if s.end > times[0] and s.start <= times[-1]]
    return flags, sorted(shown, key=lambda s: (s.start, s.kind))


def find(
    rules: TimingRules,
    chart: Chart,
    dashas: tuple[Period, ...],
    times: list[datetime],
    track: dict[str, list[float]],
    area: str,
) -> Timing | None:
    """The stretches of `times` (one per day) in which each timing rule holds for this chart and area. None until the rules are checked."""
    if not rules.servable or area not in rules.areas:
        return None
    ch20 = house_effects.load_rules()
    signs = {p: [sign_index(x) for x in track[p]] for p in track}
    natal = {p: sign_index(chart.planets[p].longitude) for p in chart.planets}
    nav = {p: navamsa_sign(chart.planets[p].longitude) for p in chart.planets}
    lagna, moon = sign_index(chart.ascendant), natal["moon"]
    n = len(times)
    houses = rules.areas[area]
    general: list[RuleWindows] = []
    for ref_name, ref in (("lagna", lagna), ("the Moon sign", moon)):
        ll = SIGN_LORDS[ref]
        for h in houses:
            hs = (ref + h - 1) % 12
            lh = SIGN_LORDS[hs]
            lh_targets = _trines(natal[lh]) | _trines(nav[lh])
            ll_targets = _trines(natal[ll]) | _trines(nav[ll])
            same = ll == lh
            strong = house_effects.strength(ch20, lh, natal[lh]) in (
                "own",
                "moolatrikona",
                "exaltation",
            )
            conj = [signs[ll][i] == signs[lh][i] for i in range(n)]
            flags = {
                "t1": [signs[ll][i] in lh_targets for i in range(n)],
                "t2": [signs[ll][i] == hs for i in range(n)],
                "t3": [signs[lh][i] in ll_targets for i in range(n)],
                "t4": (
                    [False] * n
                    if same
                    else [
                        conj[i]
                        or _aspects(ll, signs[ll][i], signs[lh][i])
                        or _aspects(lh, signs[lh][i], signs[ll][i])
                        for i in range(n)
                    ]
                ),
                "jupiter": [signs["jupiter"][i] in lh_targets for i in range(n)],
                "conjunction": [False] * n if same or not strong else conj,
            }
            for rid in GENERAL_IDS:
                note = ""
                if rid in ("t4", "conjunction") and same:
                    note = f"does not apply: the lord of the lagna and the lord of the house are the same planet ({ll.title()})"
                elif rid == "conjunction" and not strong:
                    note = f"the text asks that the lord of the house be strong at birth; {lh.title()} is not in an own, moolatrikona or exaltation sign"
                general.append(_result(rules.general[rid], ref_name, h, flags[rid], times, note))
    marriage: list[RuleWindows] = []
    dasha_list: list[DashaWindow] = []
    m2: list[str] = []
    m3: list[str] = []
    if area == "marriage":
        seventh = (lagna + 6) % 12
        l7, ll = SIGN_LORDS[seventh], SIGN_LORDS[lagna]
        ll_targets = _trines(natal[ll]) | _trines(nav[ll])
        l7_targets = _trines(natal[l7]) | _trines(nav[l7])
        m1 = [signs["venus"][i] in ll_targets or signs[l7][i] in ll_targets for i in range(n)]
        marriage.append(_result(rules.marriage["m1"], "lagna", 7, m1, times))
        m2 = sorted(
            {p for p in natal if natal[p] == seventh}
            | {p for p in SEVEN if _aspects(p, natal[p], seventh)}
            | {l7}
        )
        f2, dasha_list = _dasha_flags(dashas, times, set(m2))
        marriage.append(_result(rules.marriage["m2"], "lagna", 7, f2, times))
        cands = {SIGN_LORDS[natal[l7]], SIGN_LORDS[nav[l7]], "venus", "moon"}
        rank = {p: STANDING_RANK[house_effects.strength(ch20, p, natal[p])] for p in cands}
        best = max(rank.values())
        m3 = sorted(p for p in cands if rank[p] == best)
        f3d, _ = _dasha_flags(dashas, times, set(m3))
        jup = [signs["jupiter"][i] in l7_targets for i in range(n)]
        marriage.append(
            _result(
                rules.marriage["m3"],
                "lagna",
                7,
                [a and b for a, b in zip(f3d, jup, strict=True)],
                times,
            )
        )
    return Timing(
        area,
        houses,
        times[0],
        times[-1],
        tuple(general),
        tuple(marriage),
        tuple(dasha_list),
        tuple(m2),
        tuple(m3),
    )
