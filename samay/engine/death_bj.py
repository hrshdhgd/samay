"""Brihat Jataka chapter XXV: the cause and manner of death, its place, the time of insensibility, what becomes of the body, and the worlds before and after.

Texts and condition definitions are in data/rules/brihat-jataka-death.yaml (quoted from the public-domain translation); the conditions are coded here. MOST SENSITIVE: the bot
shows verses 1-13 inside chart:longevity and verses 14-15 as chart:afterlife, each only after a warning and a tap. Nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .malefic_yogas import PASA, SARPA, STANDING_RANK
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-death.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
WATERY_LORDS = (
    "moon",
    "mercury",
    "jupiter",
    "venus",
)  # a drekkana's lord counted benefic for 25.13 (the Moon included)
STRONG = ("own", "moolatrikona", "exaltation")
WEAK = ("inimical", "depression")
KENDRA = (1, 4, 7, 10)
OWN_PLACE = {
    "sun": 4,
    "moon": 3,
}  # a planet's 'own sign' for 25.12: the Sun and Moon have one; the others their moolatrikona sign
SECTIONS = ("cause", "place", "body", "past", "next")


@dataclass(frozen=True)
class DeathRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    caution: str
    afterlife_frame: str
    raw: dict
    yogas: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    section: str  # cause, place, body, past or next
    id: str
    verse: str
    detail: str  # what the chart shows
    text: str  # quoted
    note: str = ""


Detect = Callable[[Ctx], str | None]


def _the(p: str) -> str:
    return f"the {p.title()}" if p in ("sun", "moon") else p.title()


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def _o(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _waning(c: Ctx) -> bool:
    return (c.chart.planets["moon"].longitude - c.chart.planets["sun"].longitude) % 360.0 > 180.0


def _rank(c: Ctx, p: str) -> int:
    return STANDING_RANK[c.stand(p)]


def _strongest(c: Ctx, planets) -> list[str]:
    planets = list(dict.fromkeys(planets))
    best = max(_rank(c, p) for p in planets)
    return [p for p in planets if _rank(c, p) == best]


def _hemmed(c: Ctx, p: str) -> bool:
    s = c.sign[p]
    return any(c.sign[m] == (s - 1) % 12 for m in MALEFICS) and any(
        c.sign[m] == (s + 1) % 12 for m in MALEFICS
    )


def _at(c: Ctx, **houses: int) -> bool:
    return all(c.house[p] == h for p, h in houses.items())


def _rising_no(c: Ctx) -> int:
    return int(degree_in_sign(c.chart.ascendant) // 10.0) + 1


def _drekkana_of_house(c: Ctx, h: int) -> tuple[int, int, str]:
    """(sign, 1-3, lord) of the drekkana in house h that corresponds to the rising one: for the 8th it is the 22nd from the rising drekkana."""
    sign, n = (c.lagna + h - 1) % 12, _rising_no(c)
    return sign, n, SIGN_LORDS[(sign + 4 * (n - 1)) % 12]


def _y_kinsmen(c: Ctx) -> str | None:
    by = [p for p in ("mars", "saturn") if c.sees(p, 5)]
    return (
        f"the Sun and the Moon are in Virgo, aspected by {_names(by)}"
        if c.sign["sun"] == 5 == c.sign["moon"] and by
        else None
    )


def _y_prison(c: Ctx) -> str | None:
    there = [p for p in MALEFICS if c.house[p] in (5, 9)]
    if len(there) >= 2 and not any(c.sees(b, c.sign[p]) for p in there for b in BENEFICS):
        return f"{_names(there)} in the 5th and 9th houses, no benefic aspecting them"
    return None


def _y_prison_drekkana(c: Ctx) -> str | None:
    sign, n, _ = _drekkana_of_house(c, 8)
    return f"the drekkana in the 8th is the {_o(n)} of {SIGNS[sign]}" if (sign, n) in SARPA | PASA else None


def _y_woman(c: Ctx) -> str | None:
    with_moon = [p for p in MALEFICS if c.sign[p] == c.sign["moon"]]
    if c.lagna == 11 and c.sign["sun"] == 11 and c.sign["moon"] == 5 and with_moon and c.sign["venus"] == 0:
        return f"lagna Pisces with the Sun; the Moon in Virgo with {_names(with_moon)}; Venus in Aries"
    return None


def _y_spear_2(c: Ctx) -> str | None:
    if _waning(c) and all(c.house[p] in (1, 5, 9) for p in ("sun", "mars", "saturn", "moon")):
        return "the Sun, Mars, Saturn and the waning Moon all in the 1st, 5th and 9th houses"
    return None


def _y_privities(c: Ctx) -> str | None:
    if _waning(c) and c.sees("mars", c.sign["moon"]) and c.stand("mars") in STRONG and c.house["saturn"] == 8:
        return f"the waning Moon aspected by Mars ({c.stand('mars')}), Saturn in the 8th"
    return None


def _yp(cond: Callable[[Ctx], bool], detail: str) -> Detect:
    return lambda c: detail if cond(c) else None


YOGAS: dict[str, Detect] = {
    "stones": _yp(
        lambda c: c.house["sun"] in (4, 10) and c.house["mars"] in (4, 10),
        "the Sun and Mars in the 4th or 10th house",
    ),
    "well": _yp(
        lambda c: _at(c, saturn=4, moon=7, mars=10),
        "Saturn in the 4th, the Moon in the 7th, Mars in the 10th",
    ),
    "kinsmen": _y_kinsmen,
    "drowning": _yp(
        lambda c: c.lagna in (2, 5, 8, 11) and c.sign["sun"] == c.lagna == c.sign["moon"],
        "the Sun and the Moon in a common rising sign",
    ),
    "dropsy": _yp(
        lambda c: c.sign["saturn"] == 3 and c.sign["moon"] == 9,
        "Saturn in Cancer, the Moon in Capricorn",
    ),
    "moon_mars_signs": _yp(
        lambda c: c.sign["moon"] in (0, 7) and _hemmed(c, "moon"),
        "the Moon in a sign of Mars, between malefics",
    ),
    "moon_virgo": _yp(
        lambda c: c.sign["moon"] == 5 and _hemmed(c, "moon"),
        "the Moon in Virgo, between malefics",
    ),
    "moon_saturn_signs": _yp(
        lambda c: c.sign["moon"] in (9, 10) and _hemmed(c, "moon"),
        "the Moon in a sign of Saturn, between malefics",
    ),
    "prison": _y_prison,
    "prison_drekkana": _y_prison_drekkana,
    "woman_at_home": _y_woman,
    "spear_1": _yp(
        lambda c: (c.house["mars"] == 4 or c.house["sun"] == 4) and c.house["saturn"] == 10,
        "Mars or the Sun in the 4th, Saturn in the 10th",
    ),
    "spear_2": _y_spear_2,
    "spear_3": _yp(
        lambda c: _at(c, sun=4, mars=10) and _waning(c) and c.sees("moon", c.sign["mars"]),
        "the Sun in the 4th, Mars in the 10th aspected by the waning Moon",
    ),
    "wood": _yp(
        lambda c: _at(c, sun=4, mars=10) and c.sees("saturn", c.sign["mars"]),
        "the Sun in the 4th, Mars in the 10th aspected by Saturn",
    ),
    "club": _yp(
        lambda c: _waning(c) and _at(c, moon=8, mars=10, saturn=1, sun=4),
        "the waning Moon in the 8th, Mars in the 10th, Saturn in the 1st, the Sun in the 4th",
    ),
    "smoke": _yp(
        lambda c: _waning(c) and _at(c, moon=10, mars=9, saturn=1, sun=5),
        "the waning Moon in the 10th, Mars in the 9th, Saturn in the 1st, the Sun in the 5th",
    ),
    "king": _yp(
        lambda c: _at(c, mars=4, sun=7, saturn=10),
        "Mars in the 4th, the Sun in the 7th, Saturn in the 10th",
    ),
    "worms": _yp(
        lambda c: _at(c, saturn=2, moon=4, mars=10),
        "Saturn in the 2nd, the Moon in the 4th, Mars in the 10th",
    ),
    "vehicle": _yp(lambda c: _at(c, sun=10, mars=4), "the Sun in the 10th, Mars in the 4th"),
    "machine": _yp(
        lambda c: _at(c, mars=7, saturn=1, moon=1),
        "Mars in the 7th, Saturn and the Moon in the lagna",
    ),
    "excrement_1": _yp(
        lambda c: c.sign["mars"] == 6 and c.sign["saturn"] == 0 and c.sign["moon"] in (9, 10),
        "Mars in Libra, Saturn in Aries, the Moon in a sign of Saturn",
    ),
    "excrement_2": _yp(
        lambda c: _waning(c) and _at(c, moon=10, sun=7, mars=4),
        "the waning Moon in the 10th, the Sun in the 7th, Mars in the 4th",
    ),
    "privities": _y_privities,
    "birds": _yp(
        lambda c: _waning(c) and _at(c, sun=7, mars=7, saturn=8, moon=4),
        "the Sun and Mars in the 7th, Saturn in the 8th, the waning Moon in the 4th",
    ),
    "mountain": _yp(
        lambda c: _at(c, sun=1, mars=5, saturn=8, moon=9),
        "the Sun in the 1st, Mars in the 5th, Saturn in the 8th, the Moon in the 9th",
    ),
}


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> DeathRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    yogas = {y["id"]: y for y in raw["yogas"]}
    if len(yogas) != len(raw["yogas"]) or set(yogas) != set(YOGAS):
        raise ValueError(f"{path.name}: the yoga ids must be exactly those the engine codes")
    for y in yogas.values():
        if not all(isinstance(y.get(f), str) and y[f].strip() for f in ("verse", "text", "definition")):
            raise ValueError(f"{path.name} {y.get('id')}: needs verse, text and definition")
    for key in ("humours", "worlds"):
        if set(raw[key]) != set(SEVEN):
            raise ValueError(f"{path.name}: {key} needs each of the seven planets")
    if not set(SEVEN) <= set(raw["occupant"]):
        raise ValueError(f"{path.name}: occupant needs each of the seven planets")
    if len(raw["limbs"]) != 12 or len(raw["place"]["places"]) != 12:
        raise ValueError(f"{path.name}: limbs and places need twelve entries, Aries first")
    return DeathRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["caution"],
        raw["afterlife_frame"],
        raw,
        yogas,
    )


def _work(r: dict, c: Ctx, p: str) -> str:
    kind = "strong" if c.stand(p) in STRONG else "weak" if c.stand(p) in WEAK else "middle"
    return f"{r['occupant']['work'][kind]} {r['occupant']['work_note']}"


def _cause(rules: DeathRules, c: Ctx) -> list[Found]:
    r = rules.raw
    s8 = (c.lagna + 7) % 12
    out: list[Found] = []
    occupants = [p for p in SEVEN if c.sign[p] == s8]
    for p in occupants:
        o = r["occupant"]
        out.append(
            Found(
                "cause",
                f"occupant_{p}",
                o["verse"],
                f"{p.title()} is in the 8th ({SIGNS[s8]}, {c.stand(p)})",
                f"{o['lead']} {o[p]}",
                _work(r, c, p),
            )
        )
    if not occupants:
        seers = c.seers(s8)
        if seers:
            top = _strongest(c, seers)
            humours = "; ".join(f"{p.title()}: {r['humours'][p]}" for p in seers)
            out.append(
                Found(
                    "cause",
                    "aspect",
                    r["aspect"]["verse"],
                    f"the 8th ({SIGNS[s8]}) is empty and aspected by {_names(seers)} (strongest: {_names(top)}); the humours: {humours}; the part of the body: the {r['limbs'][s8]}",
                    r["aspect"]["text"],
                )
            )
    for yid, detect in YOGAS.items():
        got = detect(c)
        if got:
            y = rules.yogas[yid]
            out.append(Found("cause", yid, y["verse"], got[:1].upper() + got[1:], y["text"]))
    if not out:
        sign, n, lord = _drekkana_of_house(c, 8)
        top = _strongest(c, [lord, SIGN_LORDS[s8]])
        means = "; ".join(f"{p.title()}: {r['occupant'][p].split(', ', 1)[1]}" for p in top)
        out.append(
            Found(
                "cause",
                "fallback",
                r["fallback"]["verse"],
                f"no yoga above applies; the 22nd drekkana is the {_o(n)} of {SIGNS[sign]}, lord {lord.title()}; the lord of the sign is {SIGN_LORDS[s8].title()}; the more powerful: {_names(top)} ({means})",
                r["fallback"]["text"],
            )
        )
    kind = "movable" if s8 % 3 == 0 else "fixed" if s8 % 3 == 1 else "common"
    sk = r["sign_kind"]
    out.append(
        Found(
            "cause",
            "sign_kind",
            sk["verse"],
            f"the 8th house is {SIGNS[s8]}, a {kind} sign",
            sk[kind][:1].upper() + sk[kind][1:],
        )
    )
    return out


def _own_place(c: Ctx, p: str) -> int:
    return OWN_PLACE.get(p, c.ch20.moolatrikona[p])


def _place(rules: DeathRules, c: Ctx, unrisen_minutes: float | None) -> list[Found]:
    r = rules.raw
    places = r["place"]["places"]
    lord = SIGN_LORDS[c.lagna_nav]
    cands: list[tuple[str, str, int]] = [
        (
            lord,
            f"the sign {_the(lord)} (lord of the rising navamsa) is in",
            c.sign[lord],
        )
    ]
    cands += [
        (q, f"the own sign of {_the(q)}, which is with {_the(lord)}", _own_place(c, q))
        for q in SEVEN
        if q != lord and c.sign[q] == c.sign[lord]
    ]
    cands += [
        (q, f"the own sign of {_the(q)}, which aspects {_the(lord)}", _own_place(c, q))
        for q in c.seers(c.sign[lord])
        if q != lord
    ]
    nav_lord = SIGN_LORDS[c.nav[lord]]
    cands.append(
        (
            nav_lord,
            f"the own sign of {_the(nav_lord)}, lord of the navamsa {_the(lord)} is in",
            _own_place(c, nav_lord),
        )
    )
    top = set(_strongest(c, [p for p, _, _ in cands]))
    lines = [
        f"{why}: {SIGNS[s]}, {places[s]}" + (" (the most powerful)" if p in top else "")
        for p, why, s in cands
    ]
    out = [
        Found(
            "place",
            "place",
            r["place"]["verse"],
            "; ".join(lines),
            r["place"]["text"],
            r["place"]["note"],
        )
    ]
    if unrisen_minutes is not None:
        lord_l = SIGN_LORDS[c.lagna]
        by_lord = c.sees(lord_l, c.lagna)
        by_benefic = [b for b in BENEFICS if b != lord_l and c.sees(b, c.lagna)]
        factor = 6 if by_lord and by_benefic else 2 if by_lord else 3 if by_benefic else 1
        total = round(unrisen_minutes * factor)
        why = [f"{SIGNS[c.lagna]} had about {round(unrisen_minutes)} minutes left to rise at birth"]
        if by_lord:
            why.append(f"its lord {lord_l.title()} aspects it")
        if by_benefic:
            why.append(f"{_names(by_benefic)} {'aspects' if len(by_benefic) == 1 else 'aspect'} it")
        out.append(
            Found(
                "place",
                "insensibility",
                r["insensibility"]["verse"],
                "; ".join(why) + f": by the rule, about {total // 60} hours {total % 60} minutes",
                r["insensibility"]["text"],
            )
        )
    return out


def _body(rules: DeathRules, c: Ctx) -> list[Found]:
    r = rules.raw["body"]
    sign, n, lord = _drekkana_of_house(c, 8)
    lo = sign * 30.0 + (n - 1) * 10.0
    inside = [p for p in SEVEN if lo <= c.chart.planets[p].longitude % 360.0 < lo + 10.0]
    benefic_lord = lord in WATERY_LORDS
    mixed = any(p in MALEFICS for p in inside) if benefic_lord else any(p in WATERY_LORDS for p in inside)
    kind = "misra" if mixed else "watery" if benefic_lord else "fiery"
    where = f"the 22nd drekkana is the {_o(n)} of {SIGNS[sign]}, lord {lord.title()}" + (
        f", with {_names(inside)} in it" if inside else ""
    )
    out = [Found("body", kind, r["verse"], f"{where}: a {kind} drekkana", r[kind], r["note"])]
    if (sign, n) in SARPA:
        out.append(
            Found(
                "body",
                "sarpa",
                r["verse"],
                f"the {_o(n)} drekkana of {SIGNS[sign]} carries a snake (chapter XXVII)",
                r["sarpa"],
            )
        )
    return out


def _past(rules: DeathRules, c: Ctx) -> list[Found]:
    r = rules.raw
    out = []
    for light in _strongest(c, ["sun", "moon"]):
        lon = c.chart.planets[light].longitude
        n = int(degree_in_sign(lon) // 10.0)
        lord = SIGN_LORDS[(c.sign[light] + 4 * n) % 12]
        stand = c.stand(lord)
        grade = "exalted" if stand == "exaltation" else "debilitated" if stand == "depression" else "middle"
        out.append(
            Found(
                "past",
                f"past_{light}",
                r["past"]["verse"],
                f"the {light.title()} (the more powerful light) is in the {_o(n + 1)} drekkana of {SIGNS[c.sign[light]]}, lord {lord.title()}, which is in {SIGNS[c.sign[lord]]} ({stand})",
                f"The person has come from {r['worlds'][lord]}; {r['past'][grade]}",
            )
        )
    return out


def _next(rules: DeathRules, c: Ctx) -> list[Found]:
    r = rules.raw
    out = []
    in6 = [p for p in SEVEN if c.house[p] == 6]
    in8 = [p for p in SEVEN if c.house[p] == 8]
    if not in6 and not in8:
        lords = [_drekkana_of_house(c, 6)[2], _drekkana_of_house(c, 8)[2]]
        top = _strongest(c, lords)
        out.append(
            Found(
                "next",
                "next_drekkana",
                r["next"]["verse"],
                f"the 6th and 8th are empty; the lords of their drekkanas are {_names(dict.fromkeys(lords))}, the more powerful {_names(top)}",
                "The person will go to " + " or ".join(r["worlds"][p] for p in dict.fromkeys(top)),
            )
        )
    occupants = [p for p in SEVEN if c.house[p] in (6, 7, 8)]
    if occupants:
        top = _strongest(c, occupants)
        out.append(
            Found(
                "next",
                "next_occupant",
                r["next"]["verse"],
                f"{_names(occupants)} in the 6th, 7th or 8th; the most powerful {_names(top)}",
                "The person will go to " + " or ".join(dict.fromkeys(r["worlds"][p] for p in top)),
            )
        )
    s = r["salvation"]
    if c.house["jupiter"] in (*KENDRA, 6, 8) and c.stand("jupiter") == "exaltation":
        out.append(
            Found(
                "next",
                "salvation",
                s["verse"],
                f"Jupiter is exalted in the {_o(c.house['jupiter'])} house",
                s["text"],
            )
        )
    elif (
        c.lagna == 11
        and c.sign["jupiter"] == 11
        and SIGN_LORDS[c.nav["jupiter"]] in BENEFICS
        and all(c.stand(p) in WEAK for p in SEVEN if p != "jupiter")
    ):
        out.append(
            Found(
                "next",
                "salvation",
                s["verse"],
                f"lagna Pisces with Jupiter in it, in the navamsa of {SIGNS[c.nav['jupiter']]}, the other planets weak",
                s["text"],
            )
        )
    return out


def find(rules: DeathRules, chart: Chart, unrisen_minutes: float | None = None) -> tuple[Found, ...] | None:
    """Everything chapter XXV says of this chart, by section. `unrisen_minutes` is the time the rising sign still had to rise at birth (from the ephemeris), for the period of
    insensibility; without it that line is left out. None until the rules are checked.
    """
    if not rules.servable:
        return None
    c = Ctx(chart)
    return tuple(
        _cause(rules, c)
        + _place(rules, c, unrisen_minutes)
        + _body(rules, c)
        + _past(rules, c)
        + _next(rules, c)
    )
