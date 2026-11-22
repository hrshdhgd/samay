"""Brihat Jataka chapter VIII: the Kendradi life-periods laid over the span of chapter VII: their order and length, the names that mark each good, bad or mixed, and what each planet's good
and bad period brings. MOST SENSITIVE: shown inside chart:longevity only after a warning and a tap. Texts in data/rules/brihat-jataka-ayurdasa.yaml; conditions coded here. Nothing is
returned until the file is checked."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import ayurdaya_bj
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .malefic_yogas import STANDING_RANK
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vedic import SIGN_LORDS, degree_in_sign, house_from

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-ayurdasa.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
GROUP = {1: 0, 4: 0, 7: 0, 10: 0, 2: 1, 5: 1, 8: 1, 11: 1, 3: 2, 6: 2, 9: 2, 12: 2}
NAMES = (
    "sampoorna",
    "poorna",
    "rikta",
    "anishta",
    "avarohini",
    "madhyama",
    "arohini",
    "adhama",
    "misraphala",
)


@dataclass(frozen=True)
class AyurdasaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    raw: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Period:
    who: str  # a planet, or "lagna"
    years: float
    start: float
    name: str
    nature: str  # good, bad or mixed
    result: str


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AyurdasaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["names"]) != set(NAMES) or any(
        n["nature"] not in ("good", "bad", "mixed") for n in raw["names"].values()
    ):
        raise ValueError(
            f"{path.name}: names must be exactly {NAMES}, each good, bad or mixed"
        )
    if set(raw["results"]) != set(SEVEN) | {"verse", "mixed"} or any(
        set(raw["results"][p]) != {"good", "bad"} for p in SEVEN
    ):
        raise ValueError(
            f"{path.name}: results needs good and bad for each of the seven planets"
        )
    if any(len(raw["lagna_period"][k]) != 3 for k in ("common", "movable", "fixed")):
        raise ValueError(
            f"{path.name}: lagna_period needs three names for each kind of sign"
        )
    return AyurdasaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw,
    )


def _arc_forward(a: float, b: float) -> float:
    return (b - a) % 360.0


def _name(r: dict, c: Ctx, p: str) -> str:
    lon = c.chart.planets[p].longitude
    exalt = r["raw_exalt"][p]
    stand = c.stand(p)
    nav_lord = SIGN_LORDS[c.nav[p]]
    nav_stand_good = (
        nav_lord == p
        or nav_lord in c.ch20.friends[p]
        or c.nav[p] == c.ch20.exaltation[p]
        or c.nav[p] == c.sign[p]
    )
    nav_bad = (
        nav_lord != p
        and nav_lord not in c.ch20.friends[p]
        and nav_lord not in c.ch20.neutrals[p]
    )
    arc = min(abs(lon - exalt), 360.0 - abs(lon - exalt))
    if arc <= 1.0:
        return "sampoorna"
    if stand == "depression" and arc >= 179.0 and nav_bad:
        return "anishta"
    if stand == "exaltation":
        return "poorna"
    if stand == "depression":
        return "misraphala" if nav_stand_good else "rikta"
    if stand == "inimical" and nav_stand_good:
        return "misraphala"
    if (
        nav_bad
        and stand in ("own", "moolatrikona", "friendly", "exaltation")
        and c.sign[p] != c.ch20.exaltation[p]
    ):
        return "misraphala"
    forward = _arc_forward(exalt, lon) <= 180.0
    if forward:
        return "madhyama" if nav_stand_good else "avarohini"
    return "adhama" if nav_bad else "arohini"


def find(rules: AyurdasaRules, chart: Chart) -> tuple[Period, ...] | None:
    """The life-periods in the book's order, with years, name and the quoted result. None until the rules are checked."""
    if not rules.servable:
        return None
    r = dict(rules.raw)
    ay = ayurdaya_bj.load_rules()
    r["raw_exalt"] = ay.raw["exaltation_degree"]
    c = Ctx(chart)
    method = ayurdaya_bj._pinda(ay.raw, c)
    years = {w.lower(): after for w, _, after, _ in method.rows}
    lagna_rank = STANDING_RANK[c.stand(SIGN_LORDS[c.lagna])]
    cands = [
        ("lagna", lagna_rank),
        ("sun", STANDING_RANK[c.stand("sun")]),
        ("moon", STANDING_RANK[c.stand("moon")]),
    ]
    first = max(cands, key=lambda x: x[1])[0]
    start_sign = c.lagna if first == "lagna" else c.sign[first]
    rest = [p for p in SEVEN if p != first]
    rest.sort(
        key=lambda p: (
            GROUP[house_from(start_sign, c.sign[p])],
            -STANDING_RANK[c.stand(p)],
            -years[p],
            SEVEN.index(p),
        )
    )
    order = [first, *rest] if first != "lagna" else ["lagna", *rest]
    out, age = [], 0.0
    for w in order:
        if w == "lagna":
            kind = {0: "movable", 1: "fixed", 2: "common"}[c.lagna % 3]
            name = r["lagna_period"][kind][
                int(degree_in_sign(chart.ascendant) // 10.0)
            ].lower()
            nature = {"uttama": "good", "madhyama": "mixed", "adhama": "bad"}[name]
            res = r["results"][SIGN_LORDS[c.lagna]]
        else:
            name = _name(r, c, w)
            nature = r["names"][name]["nature"]
            res = r["results"][w]
        text = (
            res["good"]
            if nature == "good"
            else (
                res["bad"]
                if nature == "bad"
                else f"{res['good']}. And: {res['bad'][:1].lower() + res['bad'][1:]}"
            )
        )
        out.append(Period(w, years[w], age, name, nature, text))
        age += years[w]
    return tuple(out)
