"""Brihat Jataka chapter V: the circumstances of a birth (father and mother, twins, the cord, the place, the delivery room, the lamp, the midwives).

Texts and condition definitions are in data/rules/brihat-jataka-birth.yaml (quoted from the public-domain translation); the conditions are coded here, one detector per rule id.
Two groups: "birth" (chart:birth) and "parents" (chart:birth_parents, SENSITIVE: illegitimacy and a deserted child). Nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .malefic_yogas import STANDING_RANK
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign, house_from

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-birth.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
STRONG = ("own", "moolatrikona", "exaltation")
GROUPS = ("birth", "parents")
MARS_DREKKANAS = {(0, 1), (3, 2), (4, 3), (7, 1), (8, 2), (11, 3)}
KIND = {0: "movable", 1: "fixed", 2: "common"}


@dataclass(frozen=True)
class BirthRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    parents_frame: str
    raw: dict
    rules: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    id: str
    group: str
    verse: str
    detail: str  # what the chart shows
    text: str  # quoted


Detect = Callable[[Ctx], "str | tuple[str, str] | None"]


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def _kind(sign: int) -> str:
    return KIND[sign % 3]


def _watery(lon: float) -> bool:
    s = int(lon % 360.0 // 30.0)
    return s in (3, 11) or (s == 9 and degree_in_sign(lon) < 15.0)


def _biped(lon: float) -> bool:
    s = int(lon % 360.0 // 30.0)
    return s in (2, 5, 6, 10) or (s == 8 and degree_in_sign(lon) < 15.0)


def _waning(c: Ctx) -> bool:
    return (c.chart.planets["moon"].longitude - c.chart.planets["sun"].longitude) % 360.0 > 180.0


def _drek(lon: float) -> tuple[int, int]:
    return int(lon % 360.0 // 30.0), int(degree_in_sign(lon) // 10.0) + 1


def _third(lon: float) -> int:
    return int(degree_in_sign(lon) // 10.0)


def _rank(c: Ctx, p: str) -> int:
    return STANDING_RANK[c.stand(p)]


def _strongest(c: Ctx, planets) -> list[str]:
    best = max(_rank(c, p) for p in planets)
    return [p for p in planets if _rank(c, p) == best]


def _moon_sees_lagna(c: Ctx) -> bool:
    return c.house["moon"] == 7


def _d_father_away_moon(c: Ctx) -> str | None:
    return "the Moon is not in the 7th, so she does not aspect the lagna" if not _moon_sees_lagna(c) else None


def _d_father_abroad(c: Ctx) -> tuple[str, str] | None:
    if _moon_sees_lagna(c) or c.house["sun"] not in (8, 9):
        return None
    s = c.sign["sun"]
    where = {
        "movable": "the father would be in a foreign country",
        "fixed": "the father would be in his own country",
        "common": "the father would be returning to his country",
    }[_kind(s)]
    return (
        f"the Sun is in the {c.house['sun']}th, {SIGNS[s]}, a {_kind(s)} sign",
        f"The Moon not aspecting the lagna and the Sun in the {c.house['sun']}th: {where}",
    )


def _d_father_planets(c: Ctx) -> str | None:
    m = c.sign["moon"]
    between = (c.sign["mercury"] in ((m - 1) % 12, m) and c.sign["venus"] in ((m + 1) % 12, m)) or (
        c.sign["venus"] in ((m - 1) % 12, m) and c.sign["mercury"] in ((m + 1) % 12, m)
    )
    why = [
        t
        for ok, t in (
            (c.house["saturn"] == 1, "Saturn is in the lagna"),
            (c.house["mars"] == 7, "Mars is in the 7th"),
            (between, "the Moon is between Mercury and Venus"),
        )
        if ok
    ]
    return "; ".join(why) if why else None


def _d_serpent_issue(c: Ctx) -> str | None:
    d = _drek(c.chart.planets["moon"].longitude)
    ben2 = [p for p in BENEFICS if c.house[p] == 2]
    ben11 = [p for p in BENEFICS if c.house[p] == 11]
    return (
        f"the Moon is in the {d[1]}th drekkana of {SIGNS[d[0]]}, a drekkana of Mars; {_names(ben2)} in the 2nd, {_names(ben11)} in the 11th"
        if d in MARS_DREKKANAS and ben2 and ben11
        else None
    )


def _d_serpent_coiled(c: Ctx) -> str | None:
    d = _drek(c.chart.ascendant)
    return (
        f"the lagna is {SIGNS[c.lagna]} and the rising drekkana is the {d[1]}th of it, a drekkana of Mars"
        if (c.lagna in (0, 4, 7) or (c.lagna == 3 and _waning(c))) and d in MARS_DREKKANAS
        else None
    )


def _d_cord(c: Ctx) -> tuple[str, str] | None:
    by = [p for p in ("mars", "saturn") if c.sign[p] == c.lagna]
    if c.lagna not in (0, 1, 4) or not by:
        return None
    part = c.rules["limbs"][c.lagna_nav]
    return (
        f"the lagna is {SIGNS[c.lagna]} with {_names(by)} in it; the rising navamsa is that of {SIGNS[c.lagna_nav]}",
        f"The child will be born with the umbilical cord twined round the {part}",
    )


def _d_custody(c: Ctx) -> tuple[str, str] | None:
    s = c.sign["mars"]
    if c.sign["saturn"] != s:
        return None
    malefic_sign = (
        s in (0, 4, 7, 9, 10) or (s == 3 and _waning(c)) or (s in (2, 5) and c.sign["mercury"] == s)
    )
    if not malefic_sign or house_from(c.sign["sun"], s) not in (5, 7, 9):
        return None
    where = {
        "movable": "in foreign lands",
        "fixed": "in his own country",
        "common": "on his way to his native country",
    }[_kind(c.sign["sun"])]
    return (
        f"Mars and Saturn are together in {SIGNS[s]}, the {house_from(c.sign['sun'], s)}th from the Sun",
        f"The father of the child will be in custody at the time, {where}",
    )


def _d_boat_cancer(c: Ctx) -> str | None:
    return (
        "the Moon is nearly full in Cancer, Mercury in the lagna, Jupiter in the 4th"
        if c.full_moon and c.sign["moon"] == 3 and c.sign["mercury"] == c.lagna and c.house["jupiter"] == 4
        else None
    )


def _d_boat_watery(c: Ctx) -> str | None:
    return (
        f"the lagna is {SIGNS[c.lagna]}, a watery sign, and the Moon is in the 7th"
        if _watery(c.chart.ascendant) and c.house["moon"] == 7
        else None
    )


def _d_bank(c: Ctx) -> str | None:
    if not _watery(c.chart.ascendant):
        return None
    moon = c.chart.planets["moon"].longitude
    why = [
        t
        for ok, t in (
            (_watery(moon), "the Moon is in a watery sign"),
            (
                c.full_moon and c.house["moon"] == 7,
                "the Moon is full and aspects the lagna",
            ),
            (c.house["moon"] in (10, 4, 1), f"the Moon is in the {c.house['moon']}th"),
        )
        if ok
    ]
    return f"the lagna is {SIGNS[c.lagna]}, a watery sign; " + "; ".join(why) if why else None


def _d_prison(c: Ctx) -> str | None:
    by = [p for p in ("sun", "mars") if c.sees(p, c.sign["saturn"])]
    return (
        f"the Moon is in the lagna, Saturn in the 12th, aspected by {_names(by)}"
        if c.house["moon"] == 1 and c.house["saturn"] == 12 and by
        else None
    )


def _d_ditch(c: Ctx) -> str | None:
    return (
        f"the lagna is {SIGNS[c.lagna]} with Saturn in it and the Moon in the 7th"
        if c.lagna in (3, 7) and c.sign["saturn"] == c.lagna and c.house["moon"] == 7
        else None
    )


def _d_watery_saturn(c: Ctx) -> tuple[str, str] | None:
    if not _watery(c.chart.ascendant) or c.sign["saturn"] != c.lagna:
        return None
    place = {"mercury": "a pleasure house", "sun": "a temple", "moon": "sterile ground"}
    got = [p for p in place if c.house[p] == 7]
    return (
        (
            f"the lagna is {SIGNS[c.lagna]} with Saturn in it, aspected by {_names(got)}",
            "The birth will occur in " + " or ".join(place[p] for p in got),
        )
        if got
        else None
    )


def _d_biped_saturn(c: Ctx) -> tuple[str, str] | None:
    if not _biped(c.chart.ascendant) or c.sign["saturn"] != c.lagna:
        return None
    s = c.sign["saturn"]
    places = []
    if c.sees("mars", s):
        places.append("a cremation ground")
    if c.sees("venus", s) and c.sees("moon", s):
        places.append("some beautiful and agreeable spot")
    if c.sees("jupiter", s):
        places.append("the Agnihotra hall")
    if c.sees("sun", s):
        places.append("the King's palace, a temple or a cow shed")
    if c.sees("mercury", s):
        places.append("an artist's working room")
    return (
        (
            f"the lagna is {SIGNS[c.lagna]}, a biped sign, with Saturn in it",
            "The birth will occur in " + " or ".join(places),
        )
        if places
        else None
    )


def _bigger_sign(c: Ctx) -> int:
    lord_a, lord_b = SIGN_LORDS[c.lagna], SIGN_LORDS[c.lagna_nav]
    return c.lagna_nav if _rank(c, lord_b) > _rank(c, lord_a) else c.lagna


def _d_place(c: Ctx) -> tuple[str, str] | None:
    s = _bigger_sign(c)
    k = _kind(s)
    where = {
        "movable": "on roads",
        "fixed": "within a building",
        "common": "in the outer verandah",
    }[k]
    mother = (
        "; the rising navamsa is vargottama, so the house will be the mother's own property"
        if c.lagna_nav == c.lagna
        else ""
    )
    return (
        f"the stronger of the lagna and the rising navamsa is {SIGNS[s]}, a {k} sign",
        f"The birth will occur in {c.rules['places'][SIGNS[s]]}; {where}{mother}",
    )


def _d_dark(c: Ctx) -> str | None:
    why = [
        t
        for ok, t in (
            (c.nav["moon"] in (9, 10), "the Moon is in a navamsa of Saturn"),
            (c.house["moon"] == 4, "the Moon is in the 4th"),
            (c.sees("saturn", c.sign["moon"]), "Saturn aspects the Moon"),
            (c.nav["moon"] in (3, 11), "the Moon is in a watery navamsa"),
            (c.sign["moon"] == c.sign["saturn"], "the Moon is with Saturn"),
        )
        if ok
    ]
    if not why or (c.stand("sun") in STRONG and c.sees("mars", c.sign["sun"])):
        return None
    return "; ".join(why)


def _d_bare(c: Ctx) -> str | None:
    weak = [p for p in SEVEN if c.stand(p) == "depression"]
    return f"{_names(weak)} are in their depression signs" if len(weak) >= 3 else None


def _d_travail(c: Ctx) -> str | None:
    there = [p for p in MALEFICS if c.house[p] in (4, 7)]
    return f"{_names(there)} in the 4th or 7th" if there else None


def _d_house_state(c: Ctx) -> tuple[str, str] | None:
    top = _strongest(c, SEVEN)
    return (
        f"the most powerful planet: {_names(top)}",
        "The birth will occur in "
        + " or ".join(
            dict.fromkeys(c.rules["house_of_planet"][p] for p in top if p in c.rules["house_of_planet"])
        ),
    )


def _d_room(c: Ctx) -> tuple[str, str] | None:
    s = _bigger_sign(c)
    d = next(k for k, v in c.rules["directions"].items() if SIGNS[s] in v)
    return (
        f"the stronger of the lagna and the rising navamsa is {SIGNS[s]}",
        f"The delivery room will be in the {d} portion of the house",
    )


def _d_bed(c: Ctx) -> tuple[str, str] | None:
    d = c.rules["bed"][SIGNS[c.lagna]]
    return (
        f"the lagna is {SIGNS[c.lagna]}",
        f"The bed of the woman in labour will be in the {d} portion of the room",
    )


def _d_midwives(c: Ctx) -> tuple[str, str] | None:
    m = c.house["moon"]
    between = [p for p in SEVEN if p != "moon" and c.house[p] < m]
    if not between:
        return None
    weight = {
        p: (
            3
            if c.stand(p) == "exaltation" or c.chart.planets[p].retrograde
            else 2
            if c.stand(p) in ("own", "moolatrikona")
            else 1
        )
        for p in between
    }
    outside = sum(weight[p] for p in between if c.house[p] >= 7)
    inside = sum(weight[p] for p in between if c.house[p] < 7)
    kind = (
        "beautiful, well dressed women"
        if all(p in BENEFICS for p in between)
        else (
            "dirty, ugly women without ornaments"
            if all(p in MALEFICS for p in between)
            else "women of mixed looks"
        )
    )
    return (
        f"{_names(between)} stand between the lagna and the Moon",
        f"There will be {outside} midwives outside the room and {inside} inside (some reverse this), {kind}",
    )


def _third_word(lon: float, words) -> str:
    return words[_third(lon)]


def _d_oil(c: Ctx) -> tuple[str, str] | None:
    lon = c.chart.planets["moon"].longitude
    return (
        f"the Moon is in the {('first', 'middle', 'last')[_third(lon)]} third of {SIGNS[c.sign['moon']]}",
        "The oil of the lamp will be " + _third_word(lon, ("full", "one-half", "none")),
    )


def _d_wick(c: Ctx) -> tuple[str, str] | None:
    lon = c.chart.ascendant
    return (
        f"the lagna is in the {('first', 'middle', 'last')[_third(lon)]} third of {SIGNS[c.lagna]}",
        "The wick will be " + _third_word(lon, ("long and unburnt", "half burnt", "nearly wholly burnt")),
    )


def _d_lamp(c: Ctx) -> tuple[str, str] | None:
    k = _kind(c.sign["sun"])
    return (
        f"the Sun is in {SIGNS[c.sign['sun']]}, a {k} sign",
        "The lamp will be "
        + {
            "fixed": "fixed in some place",
            "movable": "carried by someone in the hand",
            "common": "a swinging lamp",
        }[k],
    )


def _d_illegitimate(c: Ctx) -> str | None:
    lagna_s, moon_s = c.lagna, c.sign["moon"]
    jup_sees = lambda s: c.sees("jupiter", s) or c.sign["jupiter"] == s
    with_sun = c.sign["moon"] == c.sign["sun"]
    bad = (
        (not jup_sees(lagna_s) and not jup_sees(moon_s))
        or (with_sun and not jup_sees(moon_s))
        or (with_sun and any(c.sign[p] == moon_s for p in ("mars", "saturn")))
    )
    saved = (
        c.lagna_nav in (8, 11)
        or c.nav["moon"] in (8, 11)
        or SIGN_LORDS[moon_s] == "jupiter"
        or c.sign["jupiter"] == moon_s
        or SIGN_LORDS[(moon_s + 4 * (_third(c.chart.planets["moon"].longitude))) % 12] == "jupiter"
    )
    if not bad or saved:
        return None
    return (
        "Jupiter does not aspect the lagna and the Moon"
        if not with_sun
        else "the Moon is with the Sun and Jupiter does not aspect, or a malefic is with them"
    )


def _d_deserted(c: Ctx) -> tuple[str, str] | None:
    if c.sign["mars"] != c.sign["saturn"]:
        return None
    lum = [p for p in ("sun", "moon") if house_from(c.sign["mars"], c.sign[p]) in (5, 9)]
    if not lum:
        return None
    kind = (
        "will live long and in comfort"
        if any(c.sees("jupiter", c.sign[p]) for p in lum)
        else "will be deserted by its mother"
    )
    return (
        f"Mars and Saturn are together in {SIGNS[c.sign['mars']]}; {_names(lum)} in the 5th or 9th from them",
        f"The child {kind}" + (", though abandoned by its mother" if "live" in kind else ""),
    )


def _d_deserted_dies(c: Ctx) -> str | None:
    if c.house["moon"] != 1 or c.sees("jupiter", c.sign["moon"]):
        return None
    if c.house["mars"] == 7 and any(c.sees(p, c.sign["moon"]) for p in ("mars", "saturn")):
        return "the Moon is in the lagna, Mars in the 7th aspecting her"
    if (
        house_from(c.sign["moon"], c.sign["mars"]) == 11
        and house_from(c.sign["moon"], c.sign["saturn"]) == 11
    ):
        return "the Moon is in the lagna with Mars and Saturn in the 11th from her"
    return None


DETECTORS: dict[str, Detect] = {
    "father_away_moon": _d_father_away_moon,
    "father_abroad": _d_father_abroad,
    "father_away_planets": _d_father_planets,
    "serpent_issue": _d_serpent_issue,
    "serpent_coiled": _d_serpent_coiled,
    "cord": _d_cord,
    "father_custody": _d_custody,
    "boat_cancer": _d_boat_cancer,
    "boat_watery": _d_boat_watery,
    "water_bank": _d_bank,
    "prison_birth": _d_prison,
    "ditch": _d_ditch,
    "watery_saturn": _d_watery_saturn,
    "biped_saturn": _d_biped_saturn,
    "place_of_sign": _d_place,
    "dark_spot": _d_dark,
    "bare_ground": _d_bare,
    "travail": _d_travail,
    "house_state": _d_house_state,
    "delivery_room": _d_room,
    "bed": _d_bed,
    "midwives": _d_midwives,
    "lamp_oil": _d_oil,
    "lamp_wick": _d_wick,
    "lamp_kind": _d_lamp,
    "illegitimate": _d_illegitimate,
    "deserted": _d_deserted,
    "deserted_dies": _d_deserted_dies,
}


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> BirthRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rules = {r["id"]: r for r in raw["rules"]}
    if len(rules) != len(raw["rules"]) or set(rules) != set(DETECTORS):
        raise ValueError(f"{path.name}: the rule ids must be exactly those the engine codes")
    for r in rules.values():
        if r.get("group") not in GROUPS or not all(
            isinstance(r.get(f), str) and r[f].strip() for f in ("verse", "text", "definition")
        ):
            raise ValueError(f"{path.name} {r.get('id')}: needs a group, verse, text and definition")
    if list(raw["places"]) != SIGNS or list(raw["bed"]) != SIGNS or len(raw["limbs"]) != 12:
        raise ValueError(
            f"{path.name}: places and bed need the twelve signs, Aries first, and limbs twelve entries"
        )
    if set(raw["house_of_planet"]) != set(SEVEN):
        raise ValueError(f"{path.name}: house_of_planet needs the seven planets")
    return BirthRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw["parents_frame"],
        raw,
        rules,
    )


def find(rules: BirthRules, chart: Chart, group: str) -> tuple[Found, ...] | None:
    """The chapter V statements of one group ("birth" or "parents") that hold for this chart, in the book's order. None until the rules are checked."""
    if not rules.servable:
        return None
    c = Ctx(chart)
    c.rules = rules.raw  # the tables the detectors read
    out: list[Found] = []
    for rid, rule in rules.rules.items():
        if rule["group"] != group:
            continue
        got = DETECTORS[rid](c)
        if got is None:
            continue
        detail, text = got if isinstance(got, tuple) else (got, rule["text"])
        out.append(Found(rid, group, rule["verse"], detail[:1].upper() + detail[1:], text))
    return tuple(out)
