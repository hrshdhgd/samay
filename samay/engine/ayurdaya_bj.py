"""Brihat Jataka chapter VII: the two methods of Ayurdaya (Pindayurdaya and Satyacharya's), the book's arithmetic for a span of life. MOST SENSITIVE: shown inside chart:longevity
only after a warning and a tap. Texts in data/rules/brihat-jataka-ayurdaya.yaml; the arithmetic is coded here. Nothing is returned until the file is checked."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .malefic_yogas import STANDING_RANK
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vedic import SIGN_LORDS, degree_in_sign, house_from

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-ayurdaya.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
STRONG = ("own", "moolatrikona", "exaltation")
CHAKRA = {12: 1.0, 11: 1 / 2, 10: 1 / 3, 9: 1 / 4, 8: 1 / 5, 7: 1 / 6}
NAV = 360.0 / 108.0  # degrees in a navamsa


@dataclass(frozen=True)
class AyurRules:
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
class Method:
    name: str
    verse: str
    rows: tuple[
        tuple[str, float, float, str], ...
    ]  # (who, years before reductions, years after, note)
    total: float
    reductions: tuple[str, ...]


@dataclass(frozen=True)
class Ayurdaya:
    methods: tuple[Method, ...]
    beyond: str | None


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AyurRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["max_years"]) != set(SEVEN) or set(raw["exaltation_degree"]) != set(
        SEVEN
    ):
        raise ValueError(
            f"{path.name}: max_years and exaltation_degree need each of the seven planets"
        )
    for k in ("pinda", "satyacharya", "beyond"):
        if not raw[k].get("verse"):
            raise ValueError(f"{path.name}: {k} needs a verse")
    return AyurRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw,
    )


def _arc(a: float, b: float) -> float:
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def _pinda_years(r: dict, p: str, lon: float) -> float:
    full = r["max_years"][p]
    away = _arc(lon, r["exaltation_degree"][p])  # 0 at exaltation, 180 at depression
    return full / 2 + (full / 2) * (180.0 - away) / 180.0


def _reductions(c: Ctx, years: dict[str, float]) -> tuple[dict[str, float], list[str]]:
    """The reductions of stanzas 2 and 3, applied to each planet's own years. Returns the reduced years and notes on what was applied."""
    out, notes = dict(years), []
    for p in SEVEN:
        if c.stand(p) == "inimical" and p != "mars":
            out[p] -= years[p] / 3
            notes.append(f"{p.title()} in an inimical sign loses a third")
        if c.combust(p) and p not in ("saturn", "venus", "sun"):
            out[p] -= years[p] / 2
            notes.append(f"{p.title()} is combust and loses a half")
    by_sign: dict[int, list[str]] = {}
    for p in SEVEN:
        if house_from(c.lagna, c.sign[p]) in CHAKRA:
            by_sign.setdefault(c.sign[p], []).append(p)
    for sign, ps in by_sign.items():
        top = max(ps, key=lambda p: STANDING_RANK[c.stand(p)])
        h = house_from(c.lagna, sign)
        frac = CHAKRA[h] * (1.0 if top in MALEFICS else 0.5)
        out[top] -= years[top] * frac
        notes.append(
            f"{top.title()} in the {h}th loses {frac:.3g} of its years (Chakrapata)"
        )
    return {p: max(v, 0.0) for p, v in out.items()}, notes


def _pinda(r: dict, c: Ctx) -> Method:
    years = {p: _pinda_years(r, p, c.chart.planets[p].longitude) for p in SEVEN}
    lagna_years = degree_in_sign(c.chart.ascendant) / NAV
    years["lagna"] = lagna_years
    red, notes = _reductions(c, {p: years[p] for p in SEVEN})
    red["lagna"] = lagna_years
    total = sum(red.values())
    mal = [p for p in MALEFICS if c.sign[p] == c.lagna]
    if mal:
        nav_before = int(c.chart.ascendant // NAV)
        cut = total * nav_before / 108.0
        if any(c.sees(b, c.lagna) for b in BENEFICS):
            cut /= 2
        total -= cut
        notes.append(
            f"a malefic ({', '.join(m.title() for m in mal)}) in the rising sign: {cut:.1f} years subtracted (Krurodaya)"
        )
    rows = tuple((p.title(), years[p], red[p], "") for p in (*SEVEN, "lagna"))
    return Method("Pindayurdaya", r["pinda"]["verse"], rows, total, tuple(notes))


def _satya(r: dict, c: Ctx) -> Method:
    years, mult_notes = {}, []
    for p in SEVEN:
        lon = c.chart.planets[p].longitude
        base = (lon / NAV) % 12
        m = 1
        if c.stand(p) == "exaltation" or c.chart.planets[p].retrograde:
            m = 3
        elif (
            c.nav[p] == c.sign[p]
            or SIGN_LORDS[c.sign[p]] == p
            or SIGN_LORDS[(c.sign[p] + 4 * int(degree_in_sign(lon) // 10.0)) % 12] == p
        ):
            m = 2
        if m > 1:
            mult_notes.append(f"{p.title()} x{m}")
        years[p] = base * m
    lagna_years = (
        (c.lagna + degree_in_sign(c.chart.ascendant) / 30.0)
        if c.stand(SIGN_LORDS[c.lagna]) in STRONG
        else (c.chart.ascendant / NAV) % 12
    )
    red, notes = _reductions(c, years)
    red["lagna"] = lagna_years
    rows = tuple(
        (p.title(), years.get(p, lagna_years), red[p], "") for p in (*SEVEN, "lagna")
    )
    return Method(
        "Satyacharya's method",
        r["satyacharya"]["verse"],
        rows,
        sum(red.values()),
        tuple(mult_notes + notes),
    )


def find(rules: AyurRules, chart: Chart) -> Ayurdaya | None:
    """Both methods' totals and working, and whether the chart is the one stanza 14 puts beyond calculation. None until the rules are checked."""
    if not rules.servable:
        return None
    c = Ctx(chart)
    r = rules.raw
    beyond = None
    if (
        c.lagna == 3
        and c.sign["jupiter"] == 3
        and c.sign["moon"] == 3
        and c.house["mercury"] in (1, 4, 7, 10)
        and c.house["venus"] in (1, 4, 7, 10)
        and all(c.house[p] in (11, 6, 3) for p in ("sun", "mars", "saturn"))
    ):
        beyond = r["beyond"]["text"]
    return Ayurdaya((_pinda(r, c), _satya(r, c)), beyond)
