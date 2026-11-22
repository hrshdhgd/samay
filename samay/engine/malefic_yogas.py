"""Brihat Jataka chapter XXIII: the old book's list of afflictions (wife and sons, disease, disability, servitude, imprisonment).

Texts and condition definitions are in data/rules/brihat-jataka-malefic-yogas.yaml (quoted from the public-domain translation); the conditions are coded here, one detector
per rule id. SENSITIVE: the bot shows this only after a warning and a tap. Nothing is returned until a person has checked the file.
"""

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
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-malefic-yogas.yaml"
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
FOUR = (
    "sun",
    "moon",
    "mars",
    "saturn",
)  # the translator's "malefic planets" of 23.10, 23.11 and 23.16
STANDING_RANK = {
    "exaltation": 6,
    "moolatrikona": 5,
    "own": 4,
    "friendly": 3,
    "neutral": 2,
    "inimical": 1,
    "depression": 0,
}
# Drekkanas read from chapter XXVII's images: (sign index, 1-3)
AGNI = {(1, 1), (10, 2)}
NIPATA = {(6, 2), (11, 3)}
PASA = {(9, 1)}
SARPA = {
    (3, 2),
    (3, 3),
    (7, 1),
    (7, 2),
    (11, 3),
}  # figures carrying or wrapped in a snake


@dataclass(frozen=True)
class MaleficRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    rules: dict[str, dict]
    causes: dict[str, str]
    imprisonment: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    id: str
    verse: str
    detail: str  # what the chart shows
    text: str  # quoted


Detect = Callable[[Ctx], "str | tuple[str, str] | None"]


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def _hs(c: Ctx, h: int) -> int:
    return (c.lagna + h - 1) % 12


def _touch(c: Ctx, p: str, sign: int) -> bool:
    return c.sign[p] == sign or c.sees(p, sign)


def _support(c: Ctx, sign: int) -> list[str]:
    """The benefics, and the sign's own lord, that stand in the sign or aspect it."""
    return [p for p in dict.fromkeys((*BENEFICS, SIGN_LORDS[sign])) if _touch(c, p, sign)]


def _benefic_sees(c: Ctx, sign: int) -> bool:
    return any(c.sees(b, sign) for b in BENEFICS)


def _malefic_sees(c: Ctx, sign: int, among=MALEFICS) -> list[str]:
    return [p for p in among if c.sees(p, sign)]


def _waning(c: Ctx) -> bool:
    return (c.chart.planets["moon"].longitude - c.chart.planets["sun"].longitude) % 360.0 > 180.0


def _drekkana(lon: float) -> tuple[int, int]:
    return int(lon % 360.0 // 30.0), int(degree_in_sign(lon) // 10.0) + 1


def _in_houses(c: Ctx, planets, houses) -> bool:
    return sorted(c.house[p] for p in planets) == sorted(houses)


def _ms_varga(c: Ctx, p: str) -> bool:
    return SIGN_LORDS[c.sign[p]] in ("mars", "saturn") or SIGN_LORDS[c.nav[p]] in (
        "mars",
        "saturn",
    )


def _strongest(c: Ctx) -> list[str]:
    rank = {p: STANDING_RANK[c.stand(p)] for p in FOUR}
    best = max(rank.values())
    return [p for p in FOUR if rank[p] == best]


def _own_ref(c: Ctx, house: int, signs: list[tuple[str, int]], want: bool) -> str | None:
    shown = []
    for ref, s in signs:
        names = _support(c, s)
        if bool(names) == want:
            shown.append(
                f"the {house}th from {ref} ({SIGNS[s]}) "
                + (
                    f"holds or is aspected by {_names(names)}"
                    if names
                    else "has no benefic or lord in or aspecting it"
                )
            )
    return "; ".join(shown) if shown and (want or len(shown) == len(signs)) else None


def _d_house(house: int, want: bool, ordinal: str) -> Detect:
    def d(c: Ctx) -> str | None:
        signs = [
            ("the lagna", _hs(c, house)),
            ("the Moon", (c.sign["moon"] + house - 1) % 12),
        ]
        out = _own_ref(c, house, signs, want)
        return out.replace(f"the {house}th", f"the {ordinal}") if out else None

    return d


def _d_virgo(planet: str, sign: int) -> Detect:
    return lambda c: (
        f"the lagna is Virgo with the Sun in it and {planet.title()} is in {SIGNS[sign]}"
        if c.lagna == 5 and c.sign["sun"] == 5 and c.sign[planet] == sign
        else None
    )


def _d_wives_number(c: Ctx) -> tuple[str, str] | None:
    s7 = _hs(c, 7)
    if not (c.sees("moon", s7) and c.sees("saturn", s7)):
        return None
    lord = SIGN_LORDS[s7]
    n = c.nav[lord] + 1
    return (
        f"the 7th ({SIGNS[s7]}) is aspected by the Moon and Saturn; its lord {lord.title()} is in the navamsa of {SIGNS[c.nav[lord]]}, number {n}",
        f"the person will have {n} {'wife' if n == 1 else 'wives'}, the number of the navamsa occupied by the lord of the 7th counted from Aries",
    )


def _d_single_wife(c: Ctx) -> str | None:
    s7 = _hs(c, 7)
    ms = (0, 4, 7)  # navamsas of Mars (Aries, Scorpio) and the Sun (Leo)
    if c.sign["jupiter"] == s7 and c.nav["jupiter"] in ms:
        return f"Jupiter is in the 7th ({SIGNS[s7]}) in the navamsa of {SIGNS[c.nav['jupiter']]}"
    if c.sign["moon"] == s7 == c.sign["venus"] and c.nav["moon"] in ms and c.nav["venus"] in ms:
        return f"the Moon and Venus are in the 7th ({SIGNS[s7]}), in the navamsas of {SIGNS[c.nav['moon']]} and {SIGNS[c.nav['venus']]}"
    return None


def _d_several_wives(c: Ctx) -> str | None:
    s7 = _hs(c, 7)
    return (
        f"the 7th ({SIGNS[s7]}) is aspected by the Moon and Venus"
        if c.sees("moon", s7) and c.sees("venus", s7)
        else None
    )


def _venus_death(c: Ctx, before: int, after: int, kinds: set, label: str) -> str | None:
    v = c.sign["venus"]
    first = [p for p in MALEFICS if c.sign[p] == (v + before) % 12]
    second = [p for p in MALEFICS if c.sign[p] == (v + after) % 12]
    kind = _drekkana(c.chart.planets["venus"].longitude)
    if first and second and kind in kinds:
        return f"{_names(first)} and {_names(second)} flank Venus as described, and Venus is in the {('1st', '2nd', '3rd')[kind[1] - 1]} drekkana of {SIGNS[kind[0]]} ({label})"
    return None


def _d_wife_rope(c: Ctx) -> str | None:
    v = c.sign["venus"]
    near = [b for b in ("mercury", "jupiter") if _touch(c, b, v)]
    kind = _drekkana(c.chart.planets["venus"].longitude)
    return (
        "no benefic is with or aspects Venus, and Venus is in the 1st drekkana of Capricorn (rope)"
        if not near and kind in PASA
        else None
    )


def _d_one_eye(c: Ctx) -> str | None:
    s, m = c.house["sun"], c.house["moon"]
    return (
        f"the Sun is in the {s}th and the Moon in the {m}th house" if (s, m) in ((12, 6), (6, 12)) else None
    )


def _d_limbs_venus_sun(c: Ctx) -> str | None:
    return (
        f"Venus and the Sun are together in the {c.house['venus']}th house"
        if c.house["venus"] == c.house["sun"] and c.house["venus"] in (5, 7, 9)
        else None
    )


def _d_barren(c: Ctx) -> str | None:
    lon = c.chart.planets["venus"].longitude
    if (
        c.house["saturn"] == 1
        and c.house["venus"] == 7
        and c.sign["venus"] in (3, 7, 11)
        and degree_in_sign(lon) >= 80.0 / 3.0
        and not any(c.house[b] == 5 for b in ("mercury", "jupiter"))
    ):
        return f"Saturn is in the lagna; Venus is in the 7th, in the last navamsa of {SIGNS[c.sign['venus']]}; no benefic is in the 5th"
    return None


def _d_neither_1(c: Ctx) -> str | None:
    if (
        all(any(c.house[p] == h for p in MALEFICS) for h in (12, 7, 1))
        and c.house["moon"] == 5
        and _waning(c)
    ):
        return "malefics stand in the 12th, the 7th and the 1st and the Moon is waning in the 5th"
    return None


def _d_adultery(c: Ctx) -> str | None:
    vs = c.sign["venus"]
    by = [p for p in ("mars", "saturn") if c.sees(p, vs)]
    if c.house["venus"] == 7 and _ms_varga(c, "venus") and by:
        return f"Venus is in the 7th in a sign or navamsa of Mars or Saturn and {_names(by)} aspects it"
    return None


def _d_adultery_both(c: Ctx) -> str | None:
    vs = c.sign["venus"]
    by = [p for p in ("mars", "saturn") if c.sees(p, vs)]
    if _ms_varga(c, "venus") and by and all(c.house[p] == 7 for p in ("moon", "saturn", "mars")):
        return "Venus is in a sign or navamsa of Mars or Saturn and aspected by them, and the Moon, Saturn and Mars are in the 7th"
    return None


def _d_neither_2(c: Ctx) -> str | None:
    return (
        "Venus and the Moon are in one sign and Saturn and Mars are in the 7th"
        if c.sign["venus"] == c.sign["moon"] and c.house["saturn"] == 7 == c.house["mars"]
        else None
    )


def _d_late(c: Ctx) -> str | None:
    s7 = _hs(c, 7)
    pair = [(m, f) for m in ("sun", "jupiter") for f in ("moon", "venus") if c.sign[m] == c.sign[f]]
    if pair and c.house["saturn"] == 7 == c.house["mars"] and _benefic_sees(c, s7):
        m, f = pair[0]
        return f"{m.title()} and {f.title()} are together; Saturn and Mars are in the 7th and a benefic aspects it"
    return None


def _d_family(c: Ctx) -> str | None:
    if c.house["moon"] == 10 and c.house["venus"] == 7 and any(c.house[p] == 4 for p in MALEFICS):
        return "the Moon is in the 10th, Venus in the 7th and a malefic in the 4th"
    return None


def _d_servant_son(c: Ctx) -> str | None:
    return (
        "Venus is in the 12th, in the navamsa of Saturn"
        if c.house["venus"] == 12 and c.nav["venus"] in (9, 10)
        else None
    )


def _d_low_deeds(c: Ctx) -> str | None:
    s7 = _hs(c, 7)
    return (
        "the Sun and the Moon are in the 7th and Saturn aspects it"
        if c.house["sun"] == 7 == c.house["moon"] and c.sees("saturn", s7)
        else None
    )


def _d_swelling(c: Ctx) -> str | None:
    s7 = _hs(c, 7)
    by = [p for p in ("sun", "saturn") if c.sees(p, s7)]
    return (
        f"Venus and Mars are in the 7th and {_names(by)} aspects it"
        if c.house["venus"] == 7 == c.house["mars"] and by
        else None
    )


def _d_genital(c: Ctx) -> str | None:
    with_moon = [p for p in MALEFICS if c.sign[p] == c.sign["moon"]]
    return (
        f"the Moon is in the navamsa of {SIGNS[c.nav['moon']]} with {_names(with_moon)}"
        if c.nav["moon"] in (3, 7) and with_moon
        else None
    )


def _d_white_leprosy(c: Ctx) -> str | None:
    h = (c.house["saturn"], c.house["mars"])
    return (
        "the Moon is in the lagna, Saturn and Mars in the 12th and 2nd, the Sun in the 7th"
        if c.house["moon"] == 1 and h in ((12, 2), (2, 12)) and c.house["sun"] == 7
        else None
    )


def _d_limbs_mms(c: Ctx) -> str | None:
    return (
        "the Moon is in the 10th, Mars in the 7th and Saturn in the sign after the Sun"
        if c.house["moon"] == 10 and c.house["mars"] == 7 and c.sign["saturn"] == (c.sign["sun"] + 1) % 12
        else None
    )


def _d_asthma(c: Ctx) -> str | None:
    m = c.sign["moon"]
    hemmed = {c.sign["saturn"], c.sign["mars"]} == {
        (m - 1) % 12,
        (m + 1) % 12,
    } and c.sign["saturn"] != c.sign["mars"]
    return (
        "the Moon is between Saturn and Mars and the Sun is in Capricorn"
        if hemmed and c.sign["sun"] == 9
        else None
    )


def _d_pulmonary(c: Ctx) -> str | None:
    return (
        "the Sun is in Cancer or in a navamsa of Cancer" if c.sign["sun"] == 3 or c.nav["sun"] == 3 else None
    )


def _d_skeleton(c: Ctx) -> str | None:
    return (
        f"the Sun and the Moon are together in {SIGNS[c.sign['sun']]}"
        if c.sign["sun"] == c.sign["moon"] and c.sign["sun"] in (3, 4)
        else None
    )


def _d_leprosy_moon(c: Ctx) -> str | None:
    m = c.sign["moon"]
    in_nav = (m == 8 and c.nav["moon"] == 4) or c.nav["moon"] in (11, 3, 9, 0)
    both = all(c.sign[p] == m or c.sees(p, m) for p in ("saturn", "mars"))
    return (
        f"the Moon is in a navamsa of {SIGNS[c.nav['moon']]} and Saturn and Mars are with her or aspect her"
        if in_nav and both
        else None
    )


def _d_leprosy_houses(c: Ctx) -> str | None:
    for h in (5, 9):
        s = _hs(c, h)
        if s in (7, 3, 1, 9) and all(c.sign[p] == s or c.sees(p, s) for p in ("saturn", "mars")):
            return f"the {h}th house is {SIGNS[s]} and Saturn and Mars are in it or aspect it"
    return None


def _d_blind(c: Ctx) -> str | None:
    if not _in_houses(c, FOUR, (8, 6, 2, 12)):
        return None
    top = _strongest(c)
    return f"the Sun, Moon, Mars and Saturn are in the 8th, 6th, 2nd and 12th; the strongest is {_names(top)}"


def _d_deaf(c: Ctx) -> str | None:
    if _in_houses(c, FOUR, (9, 11, 3, 5)) and not any(_benefic_sees(c, c.sign[p]) for p in FOUR):
        return f"the Sun, Moon, Mars and Saturn are in the 9th, 11th, 3rd and 5th with no benefic aspect; the strongest is {_names(_strongest(c))}"
    return None


def _d_teeth(c: Ctx) -> str | None:
    s7 = _hs(c, 7)
    there = [p for p in MALEFICS if c.house[p] == 7]
    return (
        f"{_names(there)} in the 7th with no benefic aspect" if there and not _benefic_sees(c, s7) else None
    )


def _d_pair(p: str, h: int, q: str, hq: int, label: str) -> Detect:
    return lambda c: label if c.house[p] == h and c.house[q] == hq else None


def _d_idiot_sm(c: Ctx) -> str | None:
    return (
        f"Saturn is in the lagna and Mars in the {c.house['mars']}th"
        if c.house["saturn"] == 1 and c.house["mars"] in (5, 7, 9)
        else None
    )


def _d_idiot_ms(c: Ctx) -> str | None:
    return (
        "the waning Moon and Saturn are in the 12th"
        if c.house["moon"] == 12 == c.house["saturn"] and _waning(c)
        else None
    )


def _d_servitude(c: Ctx) -> tuple[str, str] | None:
    four = list(dict.fromkeys((SIGN_LORDS[c.nav["moon"]], "sun", "moon", "jupiter")))
    hit = []
    for p in four:
        nl = SIGN_LORDS[c.nav[p]]
        dep_lord = SIGN_LORDS[(c.ch20.exaltation[p] + 6) % 12]
        enemy = nl != p and nl not in c.ch20.friends[p] and nl not in c.ch20.neutrals[p]
        if nl == dep_lord or enemy:
            hit.append(p)
    if not hit:
        return None
    clause = {
        1: "such a person will serve under other men for his livelihood",
        2: "he will become a slave",
    }.get(len(hit), "the person will be the son of a slave")
    return (
        f"{len(hit)} of the four ({_names(hit)}) stand in a navamsa of the lord of their depression sign or of an enemy",
        clause,
    )


def _d_malefic_aspects(houses, who, aspecting) -> Detect:
    def d(c: Ctx) -> str | None:
        ok = [p for p in who if c.house[p] in houses]
        if not ok:
            return None
        s = c.sign[ok[0]]
        by = [p for p in aspecting if p != ok[0] and c.sees(p, s)]
        return f"{_names(ok)} in the {c.house[ok[0]]}th, aspected by {_names(by)}" if by else None

    return d


def _d_lagna_aspect(signs: set[int]) -> Detect:
    def d(c: Ctx) -> str | None:
        by = _malefic_sees(c, c.lagna)
        return (
            f"the lagna is {SIGNS[c.lagna]} and {_names(by)} aspects it" if c.lagna in signs and by else None
        )

    return d


def _prison_kind(rules: MaleficRules, sign: int) -> str:
    for k in rules.imprisonment.values():
        if SIGNS[sign] in k["signs"]:
            return k["text"]
    return ""


def _d_servant(c: Ctx) -> tuple[str, str] | None:
    there = [p for p in MALEFICS if c.house[p] == 10]
    if not there or _benefic_sees(c, _hs(c, 10)):
        return None
    rank = {
        1: "a dignified servant",
        2: "a servant of middle rank",
        3: "a servant of low rank",
    }[len(there)]
    return (
        f"{_names(there)} in the 10th with no benefic aspect",
        f"the person will be {rank}",
    )


DETECTORS: dict[str, Detect] = {
    "sons": _d_house(5, True, "5th"),
    "no_sons": _d_house(5, False, "5th"),
    "wife": _d_house(7, True, "7th"),
    "no_wife": _d_house(7, False, "7th"),
    "virgo_wife": _d_virgo("saturn", 11),
    "virgo_sons": _d_virgo("mars", 9),
    "moon_saturn_seventh": _d_pair("moon", 7, "saturn", 7, "the Moon and Saturn are both in the 7th"),
    "wives_number": _d_wives_number,
    "single_wife": _d_single_wife,
    "several_wives": _d_several_wives,
    "wife_fire": lambda c: _venus_death(c, 3, 7, AGNI, "fire"),
    "wife_fall": lambda c: _venus_death(c, -1, 1, NIPATA, "falling"),
    "wife_rope": _d_wife_rope,
    "one_eye": _d_one_eye,
    "limbs_venus_sun": _d_limbs_venus_sun,
    "barren_wife": _d_barren,
    "neither_wife_nor_sons": _d_neither_1,
    "adultery": _d_adultery,
    "adultery_both": _d_adultery_both,
    "neither_wife_nor_sons_venus_moon": _d_neither_2,
    "late_marriage": _d_late,
    "destroys_family": _d_family,
    "servant_son": _d_servant_son,
    "low_deeds": _d_low_deeds,
    "swelling": _d_swelling,
    "genital": _d_genital,
    "white_leprosy": _d_white_leprosy,
    "limbs_moon_mars_saturn": _d_limbs_mms,
    "asthma": _d_asthma,
    "pulmonary": _d_pulmonary,
    "skeleton": _d_skeleton,
    "leprosy_moon": _d_leprosy_moon,
    "leprosy_houses": _d_leprosy_houses,
    "blind": _d_blind,
    "deaf": _d_deaf,
    "deformed_teeth": _d_teeth,
    "windy": _d_pair("saturn", 7, "jupiter", 1, "Saturn is in the 7th and Jupiter in the lagna"),
    "insane": _d_pair("mars", 7, "jupiter", 1, "Mars is in the 7th and Jupiter in the lagna"),
    "idiot_saturn_mars": _d_idiot_sm,
    "idiot_moon_saturn": _d_idiot_ms,
    "servitude": _d_servitude,
    "ugly_teeth": _d_lagna_aspect({0, 1, 8}),
    "bald": _d_lagna_aspect({0, 1, 4, 7, 8, 9, 10}),
    "weak_sight": _d_malefic_aspects((5, 9), ("sun",), ("mars", "saturn")),
    "various_diseases": _d_malefic_aspects((5, 9), ("saturn",), ("sun", "mars")),
    "defective_limbs_mars": _d_malefic_aspects((5, 9), ("mars",), ("sun", "saturn")),
    "servant": _d_servant,
}


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> MaleficRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rules = {r["id"]: r for r in raw["rules"]}
    special = {"imprisonment_houses", "imprisonment_drekkana"}
    if len(rules) != len(raw["rules"]) or set(rules) != set(DETECTORS) | special:
        raise ValueError(f"{path.name}: the rule ids must be exactly those the engine codes")
    for r in rules.values():
        if not all(isinstance(r.get(f), str) and r[f].strip() for f in ("verse", "text", "definition")):
            raise ValueError(f"{path.name} {r.get('id')}: needs verse, text and definition")
    if set(raw["causes"]) != {"sun", "moon", "mars", "saturn"}:
        raise ValueError(f"{path.name}: causes needs the Sun, Moon, Mars and Saturn")
    return MaleficRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        rules,
        raw["causes"],
        raw["imprisonment"],
    )


def find(rules: MaleficRules, chart: Chart) -> tuple[Found, ...] | None:
    """The chapter XXIII rules that hold for this chart, in the book's order. None until the rules are checked."""
    if not rules.servable:
        return None
    c = Ctx(chart)
    out: list[Found] = []
    for rid, rule in rules.rules.items():
        if rid == "imprisonment_houses":
            got = (
                "the Sun, Moon, Mars and Saturn are in the 12th, 5th, 2nd and 9th"
                if _in_houses(c, FOUR, (12, 5, 2, 9))
                else None
            )
            if got:
                kind = _prison_kind(rules, c.lagna)
                got = (
                    got,
                    rule["text"]
                    + (
                        f": {kind} (translator's note, the rising sign being {SIGNS[c.lagna]})"
                        if kind
                        else ""
                    ),
                )
        elif rid == "imprisonment_drekkana":
            n = _drekkana(chart.ascendant)[1]
            sign = (c.lagna + 4 * (n - 1)) % 12
            got = None
            if (c.lagna, n) in SARPA | PASA and _malefic_sees(c, sign):
                kind = _prison_kind(rules, sign)
                got = (
                    f"the rising drekkana is the {('1st', '2nd', '3rd')[n - 1]} of {SIGNS[c.lagna]}, of the sign {SIGNS[sign]}, which {_names(_malefic_sees(c, sign))} aspects",
                    rule["text"] + (f": {kind} (translator's note)" if kind else ""),
                )
        else:
            got = DETECTORS[rid](c)
        if got is None:
            continue
        detail, text = got if isinstance(got, tuple) else (got, rule["text"])
        if rid in ("blind", "deaf"):
            top = _strongest(c)
            text += (
                "; " + "; ".join(f"{p.title()}: {rules.causes[p]}" for p in top) + " (the translator's note)"
            )
        out.append(Found(rid, rule["verse"], detail[:1].upper() + detail[1:], text))
    return tuple(out)
