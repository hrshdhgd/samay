"""Phaladeepika chapter 17: transit conditions the book links to the end of the native's life, as stretches of days.

The rules are data (data/rules/phaladeepika-ch17-exit.yaml): each names a moving planet and the points it must reach, built with the book's own constructions
(sums and differences of longitudes, Gulika, Yamakantaka, the 22nd decanate lord). This module resolves those points for a chart and marks the days on which
the mover is in a matching sign. It names no date. Hidden until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .house_timing import RuleWindows, _result
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, degree_in_sign, navamsa_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch17-exit.yaml"
MOVERS = ("saturn", "jupiter", "sun", "moon")
VIAS = ("sign", "sign_navamsa", "navamsa")
UPAGRAHAS = (
    "gulika",
    "yamakantaka",
    "dhuma",
    "vyatipata",
    "paridhi",
    "indra_dhanus",
    "upaketu",
)
PLAIN = ("lagna", "lord22", "lord22_moon", "lord_dec_lagna", *UPAGRAHAS)
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


@dataclass(frozen=True)
class ExitRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    notes: dict
    rules: tuple[dict, ...]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


class Unavailable(Exception):
    """A point the rule needs (e.g. Gulika on a day the Sun does not set) cannot be worked out for this birth."""


def _check_expr(expr: str, where: str) -> None:
    head, _, rest = expr.partition(":")
    if head in ("lord", "natal"):
        ok = (
            (rest.isdigit() and 1 <= int(rest) <= 12)
            if head == "lord"
            else rest in BODIES
        )
        if not ok:
            raise ValueError(f"{where}: bad point {expr!r}")
    elif head in ("diff", "sum", "x9"):
        parts = rest.split("-") if head == "diff" else rest.split("+")
        if len(parts) < 2 or (head == "diff" and len(parts) != 2):
            raise ValueError(f"{where}: bad point {expr!r}")
        for part in parts:
            _check_expr(part, where)
    elif head in ("lordof", "nav", "dwa"):
        _check_expr(rest, where)
    elif expr not in PLAIN:
        raise ValueError(f"{where}: unknown point {expr!r}")


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> ExitRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    seen = set()
    for r in raw["rules"]:
        where = f"{path.name} {r.get('id')}"
        if (
            r["id"] in seen
            or r.get("mover") not in MOVERS
            or not all(
                isinstance(r.get(f), str) and r[f].strip()
                for f in ("verse", "text", "definition")
            )
        ):
            raise ValueError(
                f"{where}: needs a unique id, a mover from {MOVERS}, verse, text and definition"
            )
        seen.add(r["id"])
        if r.get("when") not in (None, "day", "night"):
            raise ValueError(f"{where}: when must be day or night")
        for t in r["targets"]:
            if (
                t["via"] not in VIAS
                or not t["offsets"]
                or not all(0 <= o < 12 for o in t["offsets"])
            ):
                raise ValueError(f"{where}: bad target {t}")
            for p in t["points"]:
                _check_expr(p, where)
    return ExitRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["notes"],
        tuple(raw["rules"]),
    )


class Points:
    """Resolves the book's point expressions to longitudes for one chart."""

    def __init__(self, chart: Chart, upagraha_longitudes: dict[str, float]):
        self.chart = chart
        self.up = upagraha_longitudes
        self.lagna = chart.ascendant
        self.sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
        self.lagna_sign = sign_index(self.lagna)

    def _lord_lon(self, planet: str) -> float:
        return self.chart.planets[planet].longitude

    def _decanate_lord(self, lon: float) -> str:
        s, k = sign_index(lon), int(degree_in_sign(lon) // 10)
        return SIGN_LORDS[(s + (0, 4, 8)[k]) % 12]

    def _lord22(self, lon: float) -> str:
        n = sign_index(lon) * 3 + int(
            degree_in_sign(lon) // 10
        )  # 0-based decanate number, Aries first
        t = (n + 21) % 36  # the 22nd counting the starting decanate as the 1st
        return SIGN_LORDS[(t // 3 + (0, 4, 8)[t % 3]) % 12]

    def lon(self, expr: str) -> float:
        head, _, rest = expr.partition(":")
        if head == "lord":
            return self._lord_lon(SIGN_LORDS[(self.lagna_sign + int(rest) - 1) % 12])
        if head == "natal":
            return self._lord_lon(rest)
        if head == "diff":
            a, b = rest.split("-")
            return (self.lon(a) - self.lon(b)) % 360.0
        if head == "sum":
            return sum(self.lon(x) for x in rest.split("+")) % 360.0
        if head == "x9":
            return sum(9.0 * self.lon(x) for x in rest.split("+")) % 360.0
        if head == "lordof":
            return self._lord_lon(SIGN_LORDS[sign_index(self.lon(rest))])
        if head == "nav":
            return navamsa_sign(self.lon(rest)) * 30.0
        if head == "dwa":
            lon = self.lon(rest)
            return ((sign_index(lon) + int(degree_in_sign(lon) // 2.5)) % 12) * 30.0
        if expr == "lagna":
            return self.lagna
        if expr == "lord22":
            return self._lord_lon(self._lord22(self.lagna))
        if expr == "lord22_moon":
            return self._lord_lon(self._lord22(self.chart.planets["moon"].longitude))
        if expr == "lord_dec_lagna":
            return self._lord_lon(self._decanate_lord(self.lagna))
        if expr in self.up:
            return self.up[expr]
        raise Unavailable(expr)


def _signs(points: Points, target: dict) -> set[int]:
    out: set[int] = set()
    for expr in target["points"]:
        lon = points.lon(expr)
        bases = {
            "sign": [sign_index(lon)],
            "navamsa": [navamsa_sign(lon)],
            "sign_navamsa": [sign_index(lon), navamsa_sign(lon)],
        }[target["via"]]
        out |= {(b + o) % 12 for b in bases for o in target["offsets"]}
    return out


def find(
    rules: ExitRules,
    chart: Chart,
    times: list[datetime],
    track: dict[str, list[float]],
    upagraha_longitudes: dict[str, float],
    night: bool | None,
) -> tuple[RuleWindows, ...]:
    """The days on which each chapter 17 transit condition holds. Empty until the rules are checked."""
    if not rules.servable:
        return ()
    points = Points(chart, upagraha_longitudes)
    movers = {m: [sign_index(x) for x in track[m]] for m in MOVERS}
    out = []
    for r in rules.rules:
        if r.get("when") and night is not None and (r["when"] == "night") != night:
            continue
        try:
            sets = [_signs(points, t) for t in r["targets"]]
        except Unavailable as e:
            out.append(
                _result(
                    r,
                    "birth",
                    0,
                    [False] * len(times),
                    times,
                    f"does not apply: {e.args[0]} cannot be worked out for this birth (the Sun does not both rise and set that day)",
                )
            )
            continue
        allowed = set().union(*sets)
        out.append(
            _result(
                r,
                "birth",
                0,
                [
                    s in allowed
                    for s in movers["moon" if r["mover"] == "moon" else r["mover"]]
                ],
                times,
            )
        )
    return tuple(out)
