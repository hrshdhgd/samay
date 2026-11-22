"""Brihat Jataka chapter VI: dangers to a baby at birth, and the commentator's counter-yogas. SENSITIVE: shown inside chart:longevity only after a warning and a tap.
Texts and definitions in data/rules/brihat-jataka-balarishta.yaml (quoted); conditions coded here. Nothing is returned until checked."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vargas import hora
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-balarishta.yaml"
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
STRONG = ("own", "moolatrikona", "exaltation")
KENDRA = (1, 4, 7, 10)
LAST_NAVAMSA = 30.0 - 10.0 / 3.0
SIRODAYA = {2, 4, 5, 6, 7, 10}


@dataclass(frozen=True)
class BalaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    timing: dict
    rules: dict[str, dict]
    cancel: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    id: str
    verse: str  # "" for a counter-yoga
    detail: str
    text: str
    kind: str = "danger"  # or "cancel"


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def _mal_in(c: Ctx, h: int) -> list[str]:
    return [p for p in MALEFICS if c.house[p] == h]


def _waning(c: Ctx) -> bool:
    return (
        c.chart.planets["moon"].longitude - c.chart.planets["sun"].longitude
    ) % 360.0 > 180.0


def _hemmed(c: Ctx) -> bool:
    m = c.sign["moon"]
    return any(c.sign[p] == (m - 1) % 12 for p in MALEFICS) and any(
        c.sign[p] == (m + 1) % 12 for p in MALEFICS
    )


def _ben_sees_moon(c: Ctx) -> list[str]:
    return [b for b in BENEFICS if c.sees(b, c.sign["moon"])]


def _no_ben_kendra(c: Ctx) -> bool:
    return not any(c.house[b] in KENDRA for b in BENEFICS)


def _strong_ben_with_or_seeing(c: Ctx, sign: int) -> list[str]:
    return [
        b
        for b in BENEFICS
        if (c.sign[b] == sign or c.sees(b, sign)) and c.stand(b) in STRONG
    ]


def _full(c: Ctx) -> bool:
    return c.full_moon


def _in_last_navamsa(lon: float) -> bool:
    return degree_in_sign(lon) >= LAST_NAVAMSA


def _d_twilight(c: Ctx) -> str | None:
    lons = [c.chart.planets[p].longitude for p in MALEFICS]
    if (
        c.house["sun"] in (1, 7)
        and hora(c.chart.ascendant) == "lunar"
        and all(_in_last_navamsa(x) for x in lons)
    ):
        return "the Sun is on the horizon (1st or 7th), the lagna is in a lunar hora, and the Sun, Mars and Saturn are in the last navamsa of their signs"
    return None


def _d_four(c: Ctx) -> str | None:
    hs = [c.house["moon"], *(c.house[p] for p in MALEFICS)]
    return (
        "the Moon, the Sun, Mars and Saturn stand one in each kendra"
        if sorted(hs) == list(KENDRA)
        else None
    )


def _d_east_west(c: Ctx) -> str | None:
    east = {10, 11, 12, 1, 2, 3}
    if (
        c.lagna in (3, 7)
        and all(c.house[p] in east for p in MALEFICS)
        and all(c.house[b] not in east for b in BENEFICS)
    ):
        return f"the lagna is {SIGNS[c.lagna]}, the malefics are in the eastern half and the benefics in the western"
    return None


def _pair(a: int, b: int, label: str) -> Callable[[Ctx], str | None]:
    return lambda c: label if _mal_in(c, a) and _mal_in(c, b) else None


def _d_three_signs(c: Ctx) -> str | None:
    s7 = (c.lagna + 6) % 12
    if all(
        any(c.sign[p] == s for p in MALEFICS) for s in (c.lagna, s7, c.sign["moon"])
    ) and not _ben_sees_moon(c):
        return "malefics stand in the lagna sign, the 7th and the Moon's sign, and no benefic aspects the Moon"
    return None


def _d_waning_twelfth(c: Ctx) -> str | None:
    if (
        _waning(c)
        and c.house["moon"] == 12
        and _mal_in(c, 1)
        and _mal_in(c, 8)
        and _no_ben_kendra(c)
    ):
        return "the waning Moon in the 12th, malefics in the lagna and the 8th, no benefic in a kendra"
    return None


def _d_moon_malefic_kendra(c: Ctx) -> str | None:
    m = [p for p in MALEFICS if c.sign[p] == c.sign["moon"]]
    return (
        f"the Moon is with {_names(m)} in the {c.house['moon']}th and no benefic is in a kendra"
        if m and c.house["moon"] in (1, 7, 8, 12) and _no_ben_kendra(c)
        else None
    )


def _d_moon_sixth_eighth(c: Ctx) -> tuple[str, str] | None:
    if c.house["moon"] not in (6, 8):
        return None
    mal = [p for p in MALEFICS if c.sees(p, c.sign["moon"])]
    ben = _ben_sees_moon(c)
    if mal and not ben:
        return (
            f"the Moon is in the {c.house['moon']}th, aspected by {_names(mal)}",
            "The child will die soon after birth",
        )
    if ben and not mal:
        return (
            f"the Moon is in the {c.house['moon']}th, aspected by {_names(ben)} alone",
            "The child will die after 8 years",
        )
    if ben and mal:
        return (
            f"the Moon is in the {c.house['moon']}th, aspected by {_names(mal + ben)}",
            "The child will die 4 years after birth",
        )
    return None


def _d_lord_defeated(c: Ctx) -> str | None:
    lord = SIGN_LORDS[c.lagna]
    if lord in ("sun", "moon") or c.house[lord] != 7:
        return None
    near = [
        p
        for p in MALEFICS
        if p != lord
        and c.sign[p] == c.sign[lord]
        and abs(c.chart.planets[p].longitude - c.chart.planets[lord].longitude) <= 1.0
    ]
    return (
        f"{lord.title()}, lord of the lagna, is in the 7th within a degree of {_names(near)}"
        if near
        else None
    )


def _d_waning_lagna(c: Ctx) -> str | None:
    if (
        _waning(c)
        and c.house["moon"] == 1
        and _mal_in(c, 8)
        and all(_mal_in(c, h) for h in (4, 7, 10))
    ):
        return "the waning Moon in the lagna, a malefic in the 8th and in each of the 4th, 7th and 10th"
    return None


def _d_hemmed(c: Ctx) -> str | None:
    return (
        f"the Moon is in the {c.house['moon']}th between malefics"
        if c.house["moon"] in (4, 7, 8) and _hemmed(c)
        else None
    )


def _d_mother_too(c: Ctx) -> str | None:
    if (
        c.house["moon"] == 1
        and _hemmed(c)
        and _mal_in(c, 7)
        and _mal_in(c, 8)
        and not _strong_ben_with_or_seeing(c, c.sign["moon"])
    ):
        return "the Moon in the lagna between malefics, malefics in the 7th and 8th, no powerful benefic aspecting her"
    return None


def _d_last_navamsa(c: Ctx) -> str | None:
    return (
        "the Moon is in the last navamsa of her sign and no benefic aspects her"
        if _in_last_navamsa(c.chart.planets["moon"].longitude) and not _ben_sees_moon(c)
        else None
    )


def _d_fifth_ninth(c: Ctx) -> str | None:
    return (
        "malefics stand in the 5th and the 9th"
        if _mal_in(c, 5) and _mal_in(c, 9)
        else None
    )


def _d_moon_lagna_seventh(c: Ctx) -> str | None:
    return (
        "the Moon in the lagna and a malefic in the 7th"
        if c.house["moon"] == 1 and _mal_in(c, 7)
        else None
    )


def _d_luminary(c: Ctx) -> str | None:
    for lum in ("sun", "moon"):
        if (
            c.house[lum] == 1
            and all(_mal_in(c, h) for h in (5, 8, 9))
            and not _strong_ben_with_or_seeing(c, c.sign[lum])
        ):
            return f"the {lum.title()} in the lagna, malefics in the 5th, 8th and 9th, no powerful benefic with or aspecting it"
    return None


def _d_four_planets(c: Ctx) -> str | None:
    if (c.house["saturn"], c.house["sun"], c.house["moon"], c.house["mars"]) != (
        12,
        9,
        1,
        8,
    ):
        return None
    saved = c.house["jupiter"] == 5 and c.stand("jupiter") in STRONG
    return (
        None
        if saved
        else "Saturn in the 12th, the Sun in the 9th, the Moon in the 1st, Mars in the 8th, no powerful Jupiter aspecting them"
    )


def _d_moon_malefic_six(c: Ctx) -> str | None:
    m = [p for p in MALEFICS if c.sign[p] == c.sign["moon"]]
    if (
        not m
        or c.house["moon"] not in (5, 7, 9, 12, 1, 8)
        or _strong_ben_with_or_seeing(c, c.sign["moon"])
    ):
        return None
    return f"the Moon is with {_names(m)} in the {c.house['moon']}th, no powerful Venus, Mercury or Jupiter with or aspecting her"


DETECT: dict[str, Callable[[Ctx], str | tuple[str, str] | None]] = {
    "twilight": _d_twilight,
    "four_kendras": _d_four,
    "east_west": _d_east_west,
    "twelfth_second": _pair(12, 2, "malefics stand in the 12th and the 2nd"),
    "sixth_eighth": _pair(6, 8, "malefics stand in the 6th and the 8th"),
    "three_signs": _d_three_signs,
    "waning_twelfth": _d_waning_twelfth,
    "moon_malefic_kendra": _d_moon_malefic_kendra,
    "moon_sixth_eighth": _d_moon_sixth_eighth,
    "lord_defeated": _d_lord_defeated,
    "waning_lagna": _d_waning_lagna,
    "moon_hemmed": _d_hemmed,
    "mother_too": _d_mother_too,
    "last_navamsa": _d_last_navamsa,
    "fifth_ninth": _d_fifth_ninth,
    "moon_lagna_seventh": _d_moon_lagna_seventh,
    "luminary_lagna": _d_luminary,
    "four_planets": _d_four_planets,
    "moon_malefic_six": _d_moon_malefic_six,
}


def _c_jupiter_lagna(c):
    return c.house["jupiter"] == 1 and c.stand("jupiter") in STRONG


def _c_lord(c):
    lord = SIGN_LORDS[c.lagna]
    return (
        c.stand(lord) in STRONG
        and not any(c.sees(p, c.sign[lord]) for p in MALEFICS if p != lord)
        and any(
            c.house[b] in KENDRA and c.sees(b, c.sign[lord])
            for b in BENEFICS
            if b != lord
        )
    )


def _c_drekkana(c):
    m = c.sign["moon"]
    n = int(degree_in_sign(c.chart.planets["moon"].longitude) // 10.0)
    return c.house["moon"] == 6 and SIGN_LORDS[(m + 4 * n) % 12] in BENEFICS


def _c_full_benefic(c):
    m = c.sign["moon"]
    return (
        c.full_moon
        and any(c.sign[b] == (m - 1) % 12 for b in BENEFICS)
        and any(c.sign[b] == (m + 1) % 12 for b in BENEFICS)
    )


def _c_benefic_kendra(c):
    return any(c.house[b] in KENDRA and c.stand(b) in STRONG for b in BENEFICS)


def _c_day_night(c):
    above = c.house["sun"] >= 7
    return c.full_moon or (above and _waning(c)) or (not above and not _waning(c))


def _c_full_jupiter(c):
    return (
        c.full_moon
        and c.house["jupiter"] in KENDRA
        and c.sees("jupiter", c.sign["moon"])
    )


def _c_rahu(c):
    return c.house["rahu"] in (3, 6, 11) and any(
        c.sees(b, c.sign["rahu"]) for b in BENEFICS
    )


def _c_sirodaya(c):
    return all(c.sign[p] in SIRODAYA for p in SEVEN)


CANCEL = {
    "jupiter_lagna": _c_jupiter_lagna,
    "lagna_lord_strong": _c_lord,
    "moon_benefic_drekkana": _c_drekkana,
    "full_benefic": _c_full_benefic,
    "benefic_kendra": _c_benefic_kendra,
    "day_night": _c_day_night,
    "full_jupiter": _c_full_jupiter,
    "rahu_benefic": _c_rahu,
    "sirodaya": _c_sirodaya,
}


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> BalaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rules, cancel = {r["id"]: r for r in raw["rules"]}, {
        r["id"]: r for r in raw["cancel"]
    }
    if (
        set(rules) != set(DETECT)
        or len(rules) != len(raw["rules"])
        or set(cancel) != set(CANCEL)
        or len(cancel) != len(raw["cancel"])
    ):
        raise ValueError(
            f"{path.name}: rule ids must be exactly those the engine codes"
        )
    if not all(
        isinstance(r.get(f), str) and r[f].strip()
        for r in (*rules.values(), *cancel.values())
        for f in ("text", "definition")
    ) or not all(r.get("verse") for r in rules.values()):
        raise ValueError(
            f"{path.name}: every rule needs text and definition (and the dangers a verse)"
        )
    return BalaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw["timing"],
        rules,
        cancel,
    )


def find(rules: BalaRules, chart: Chart) -> tuple[Found, ...] | None:
    """The chapter VI dangers that hold for this chart, then (only if there is a danger) the counter-yogas that also hold. None until the rules are checked."""
    if not rules.servable:
        return None
    c = Ctx(chart)
    out: list[Found] = []
    for rid, rule in rules.rules.items():
        got = DETECT[rid](c)
        if got:
            detail, text = got if isinstance(got, tuple) else (got, rule["text"])
            out.append(Found(rid, rule["verse"], detail[:1].upper() + detail[1:], text))
    if out:
        out += [
            Found(cid, "", "this also holds in the chart", r["text"], "cancel")
            for cid, r in rules.cancel.items()
            if CANCEL[cid](c)
        ]
    return tuple(out)
