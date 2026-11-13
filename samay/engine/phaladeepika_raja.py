"""Phaladeepika chapter 7: raja yogas and the Neechabhanga cancellation of debilitation, found from a whole-sign chart.

Texts come from data/rules/phaladeepika-ch7-raja.yaml (paraphrased); conditions are coded here, each with a `definition` sentence in the YAML for the checker.
Nothing is returned until a person has checked the file.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import house_effects
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign, house_from, nakshatra, navamsa_sign, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch7-raja.yaml"
BODIES = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
SEVEN = BODIES[:7]
MALEFICS = ("sun", "mars", "saturn", "rahu", "ketu")
BENEFICS = ("mercury", "jupiter", "venus")
KENDRA = {1, 4, 7, 10}
FULL_ASPECTS = {"mars": (4, 7, 8), "jupiter": (5, 7, 9), "saturn": (3, 7, 10)}
STRONG = ("own", "moolatrikona", "exaltation")
DIGBALA = {"sun": 10, "mars": 10, "moon": 4, "venus": 4, "mercury": 1, "jupiter": 1, "saturn": 7}


@dataclass(frozen=True)
class RajaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    yogas: dict[str, dict]
    nb: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    key: str
    verse: str
    text: str
    detail: str


class Ctx:
    def __init__(self, chart: Chart):
        self.chart = chart
        self.ch20 = house_effects.load_rules()
        self.sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
        self.lagna = sign_index(chart.ascendant)
        self.house = {p: house_from(self.lagna, s) for p, s in self.sign.items()}
        self.nav = {p: navamsa_sign(chart.planets[p].longitude) for p in BODIES}
        self.lagna_nav = navamsa_sign(chart.ascendant)
        elong = (chart.planets["moon"].longitude - chart.planets["sun"].longitude) % 360.0
        self.full_moon = 144.0 <= elong <= 216.0

    def lord(self, h: int) -> str:
        return SIGN_LORDS[(self.lagna + h - 1) % 12]

    def stand(self, p: str) -> str:
        return house_effects.strength(self.ch20, p, self.sign[p])

    def strong(self, p: str) -> bool:
        return self.stand(p) in STRONG

    def combust(self, p: str) -> bool:
        return house_effects.is_astangata(self.ch20, p, self.chart)

    def sees(self, by: str, target_sign: int) -> bool:
        return by in SEVEN and self.sign[by] != target_sign and house_from(self.sign[by], target_sign) in FULL_ASPECTS.get(by, (7,))

    def seers(self, target_sign: int, among=SEVEN) -> list[str]:
        return [p for p in among if self.sees(p, target_sign)]

    def vargottama(self, p: str) -> bool:
        return self.nav[p] == self.sign[p]

    def friends(self, p: str, q: str) -> bool:
        return q in self.ch20.friends[p]

    def relation(self, p: str, q: str) -> str:
        """How q stands to p by Phaladeepika 2.21-23: the natural friendship plus the temporary one (q in the 2nd, 3rd, 4th, 10th, 11th or 12th sign from p)."""
        natural = "friend" if q in self.ch20.friends[p] else "neutral" if q in self.ch20.neutrals[p] else "enemy"
        temporary = house_from(self.sign[p], self.sign[q]) in (2, 3, 4, 10, 11, 12)
        return {("friend", True): "adhimitra", ("friend", False): "neutral", ("enemy", False): "adhishatru", ("enemy", True): "neutral",
                ("neutral", True): "friend", ("neutral", False): "enemy"}[natural, temporary]


def _o(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


Detect = Callable[[Ctx], str | None]


def _d_three_strong(c: Ctx) -> str | None:
    ps = [p for p in SEVEN if c.strong(p) and c.house[p] in KENDRA]
    return f"{_names(ps)} are in own or exaltation signs in kendras" + (" (five or more)" if len(ps) >= 5 else "") if len(ps) >= 3 else None


def _d_retro(c: Ctx) -> str | None:
    ps = [p for p in ("mars", "mercury", "jupiter", "venus", "saturn") if c.chart.planets[p].retrograde and not c.combust(p) and c.house[p] not in (6, 8, 12)]
    return f"{_names(ps)} {'is' if len(ps) == 1 else 'are'} retrograde, not combust and not in a dusthana" + (" (three or more)" if len(ps) >= 3 else "") if ps else None


def _d_digbala(c: Ctx) -> str | None:
    ps = [p for p, h in DIGBALA.items() if c.house[p] == h]
    if len(ps) >= 2:
        return f"{_names(ps)} have directional strength" + (" (four or more besides Saturn)" if len([p for p in ps if p != "saturn"]) >= 4 else "")
    return None


def _d_varg_lm(c: Ctx) -> str | None:
    seen = c.seers(c.lagna, tuple(p for p in SEVEN if p != "moon"))
    return f"the lagna and the Moon are vargottama and {_names(seen)} aspect the lagna" if c.vargottama("moon") and c.lagna == c.lagna_nav and len(seen) >= 4 else None


def _d_varg_ll(c: Ctx) -> str | None:
    ll = c.lord(1)
    return f"the lagna lord {ll.title()} is vargottama in a {c.stand(ll)} sign in the {_o(c.house[ll])}" if c.vargottama(ll) and c.house[ll] in KENDRA | {5, 9} and c.strong(ll) else None


def _d_full_aspected(c: Ctx) -> str | None:
    s = [p for p in c.seers(c.sign["moon"]) if c.strong(p)]
    return f"the Moon is nearly full and {_names(s)} (strong) aspects her" if c.full_moon and s else None


def _d_full_kendra(c: Ctx) -> str | None:
    return f"the Moon is nearly full, in the {_o(c.house['moon'])}" if c.full_moon and c.house["moon"] in (4, 7, 10) else None


def _d_venus_ashwini(c: Ctx) -> str | None:
    seen = c.seers(c.sign["venus"])
    ok = c.house["venus"] == 1 and nakshatra(c.chart.planets["venus"].longitude)[0] == 0 and len(seen) >= 3
    return f"Venus is in the lagna in Ashwini, aspected by {_names(seen)}" if ok else None


def _d_ll_second(c: Ctx) -> str | None:
    ll = c.lord(1)
    ok = ll != "venus" and c.strong(ll) and c.house[ll] == 2 and c.sign[ll] == c.sign["venus"] and c.stand("venus") not in ("depression", "inimical")
    return f"the lagna lord {ll.title()} is strong, in the 2nd with Venus" if ok else None


def _d_mars_cardinal(c: Ctx) -> str | None:
    if c.sign["mars"] == c.lagna and c.lagna in (0, 8):
        f = [p for p in c.seers(c.lagna) if c.friends("mars", p)]
        return f"Mars is in {SIGNS[c.lagna]}, the lagna, aspected by {_names(f)}" if f else None
    return None


def _d_exchange(c: Ctx) -> str | None:
    l9, l10 = c.lord(9), c.lord(10)
    return f"the 9th lord {l9.title()} is in the 10th and the 10th lord {l10.title()} is in the 9th" if l9 != l10 and c.house[l9] == 10 and c.house[l10] == 9 else None


def _d_sun_moon_sag(c: Ctx) -> str | None:
    mid = lambda p: c.sign[p] == 8 and 10.0 <= degree_in_sign(c.chart.planets[p].longitude) < 20.0
    ok = mid("sun") and mid("moon") and c.house["saturn"] == 1 and c.stand("mars") == "exaltation"
    return "the Sun and Moon are in the middle of Sagittarius, Saturn is in the lagna and Mars is exalted" if ok else None


def _d_moon_leo_nav(c: Ctx) -> str | None:
    ok = c.full_moon and c.nav["moon"] == 4 and any(c.house[p] in KENDRA for p in BENEFICS) and not any(c.house[p] in KENDRA for p in MALEFICS)
    return "the Moon is nearly full in a Leo navamsa, with a benefic in a kendra and no malefic in any kendra" if ok else None


def _d_three_own_nav(c: Ctx) -> str | None:
    ps = [p for p in SEVEN if p != "moon" and SIGN_LORDS[c.nav[p]] == p and c.stand(p) not in ("depression", "inimical")
          and any(c.sees(b, c.sign[p]) for b in BENEFICS if b != p)]
    return f"the Moon is nearly full and {_names(ps)} are each in their own navamsa, aspected by a benefic" if c.full_moon and len(ps) >= 3 else None


def _d_varg_moon(c: Ctx) -> str | None:
    s = [p for p in c.seers(c.sign["moon"]) if c.strong(p)]
    return f"the Moon is vargottama and {_names(s)} (strong) aspects her; no malefic is in the lagna" if c.vargottama("moon") and s and not any(c.house[p] == 1 for p in MALEFICS) else None


def _d_full_varg(c: Ctx) -> str | None:
    return "the Moon is nearly full and vargottama" if c.full_moon and c.vargottama("moon") else None


def _d_jm_kendra(c: Ctx) -> str | None:
    ok = c.house["jupiter"] in KENDRA and c.house["moon"] in KENDRA and c.sees("venus", c.sign["jupiter"]) and c.sees("venus", c.sign["moon"]) \
        and not any(c.stand(p) == "depression" for p in SEVEN)
    return "Jupiter and the Moon are in kendras, aspected by Venus, and no planet is debilitated" if ok else None


def _d_water(c: Ctx) -> str | None:
    ok = c.sign["moon"] in (3, 7, 11) and c.nav["moon"] == c.lagna and not any(c.house[p] in KENDRA for p in MALEFICS)
    return f"the Moon is in {SIGNS[c.sign['moon']]} and her navamsa is the lagna sign, with no malefic in a kendra" if ok else None


def _d_venus_jup(c: Ctx) -> str | None:
    return "Venus is aspected by Jupiter" if c.sees("jupiter", c.sign["venus"]) else None


def _d_jup_lagna(c: Ctx) -> str | None:
    return f"Jupiter is in the lagna, {SIGNS[c.lagna]}" if c.house["jupiter"] == 1 and c.lagna != 9 else None


def _d_ll_kendra(c: Ctx) -> str | None:
    ll = c.lord(1)
    return f"the lagna lord {ll.title()} is in a {c.stand(ll)} sign in the {_o(c.house[ll])}" if c.strong(ll) and c.house[ll] in KENDRA else None


def _d_merc(c: Ctx) -> str | None:
    return "Mercury is strong in a kendra and aspected by Jupiter" if c.strong("mercury") and c.house["mercury"] in KENDRA and c.sees("jupiter", c.sign["mercury"]) else None


def _d_exalted_friend(c: Ctx) -> str | None:
    out = []
    for p in SEVEN:
        if c.stand(p) == "exaltation":
            f = [q for q in c.seers(c.sign[p]) if c.friends(p, q)]
            if f:
                out.append(f"{p.title()} exalted, aspected by its friend {_names(f)}")
    return "; ".join(out) if out else None


def _d_sun_moon_nav(c: Ctx) -> str | None:
    return "the Sun is in a Leo navamsa and the Moon is in Cancer" if c.nav["sun"] == 4 and c.sign["moon"] == 3 else None


def _d_moon_pisces(c: Ctx) -> str | None:
    f = [p for p in c.seers(c.sign["moon"]) if c.friends("moon", p)]
    return f"the Moon is nearly full in Pisces, aspected by her friend {_names(f)}" if c.full_moon and c.sign["moon"] == 11 and f else None


def _d_moon_exalted(c: Ctx) -> str | None:
    return "the Moon is nearly full in Taurus" if c.full_moon and c.sign["moon"] == 1 else None


def _adhimitra_moon(c: Ctx) -> str | None:
    lord = SIGN_LORDS[c.nav["moon"]]
    return lord if lord != "moon" and c.relation("moon", lord) == "adhimitra" else None


def _d_adhimitra_venus(c: Ctx) -> str | None:
    lord = _adhimitra_moon(c)
    return f"the Moon is in the navamsa of {lord.title()}, her adhimitra, and Venus aspects her" if lord and c.sees("venus", c.sign["moon"]) else None


def _d_adhimitra_jupiter(c: Ctx) -> str | None:
    lord = _adhimitra_moon(c)
    return f"the Moon is in the navamsa of {lord.title()}, her adhimitra, and Jupiter aspects her" if lord and c.sees("jupiter", c.sign["moon"]) else None


def _d_four_one_sign(c: Ctx) -> str | None:
    by_sign: dict[int, list[str]] = {}
    for p in SEVEN:
        by_sign.setdefault(c.sign[p], []).append(p)
    for s, ps in by_sign.items():
        if len(ps) >= 4:
            rank = {p: ("depression", "inimical", "neutral", "friendly", "own", "moolatrikona", "exaltation").index(c.stand(p)) for p in ps}
            top = [p for p in ps if rank[p] == max(rank.values())]
            return f"{_names(ps)} are together in {SIGNS[s]}; the strongest there: {_names(top)}"
    return None


def _decanate_lord(lon: float) -> str:
    return SIGN_LORDS[(sign_index(lon) + (0, 4, 8)[int(degree_in_sign(lon) // 10)]) % 12]


def _d_moon_sat_dec(c: Ctx) -> str | None:
    ok = _decanate_lord(c.chart.planets["moon"].longitude) == "saturn" and c.sees("saturn", c.sign["moon"]) and c.sees("mars", c.sign["moon"])
    return "the Moon is in a decanate of Saturn and Saturn and Mars aspect her" if ok else None


def _d_moon_mars_nav(c: Ctx) -> str | None:
    return "the Moon is in the navamsa of Mars and Saturn aspects her" if SIGN_LORDS[c.nav["moon"]] == "mars" and c.sees("saturn", c.sign["moon"]) else None


def _d_moon_lord_sat(c: Ctx) -> str | None:
    lord = SIGN_LORDS[c.sign["moon"]]
    seen = c.seers(c.sign[lord])
    return f"the lord of the Moon's sign, {lord.title()}, is aspected by Saturn only" if seen == ["saturn"] else None


def _d_tenth_four(c: Ctx) -> str | None:
    l10 = c.lord(10)
    good = [p for p in SEVEN if c.house[p] in (1, 4, 5, 7, 9, 10)]
    return f"{_names(good)} stand in kendras or trikonas, including the 10th lord {l10.title()}" if l10 in good and len(good) >= 4 else None


def _d_m36(c: Ctx) -> str | None:
    got = {h: [p for p in ("sun", "mars", "saturn") if c.house[p] == h] for h in (3, 6, 11)}
    return "malefics are in the 3rd, 6th and 11th: " + "; ".join(f"{_names(v)} in the {_o(h)}" for h, v in got.items()) if all(got.values()) else None


def _d_mm(c: Ctx) -> str | None:
    return "Mars and Mercury are in the 2nd" if c.house["mars"] == 2 and c.house["mercury"] == 2 else None


def _d_sv(c: Ctx) -> str | None:
    return "the Sun and Venus are in the 4th" if c.house["sun"] == 4 and c.house["venus"] == 4 else None


def _d_msj(c: Ctx) -> str | None:
    return "Mars is in the 10th, Saturn in the 11th and Jupiter in the lagna" if (c.house["mars"], c.house["saturn"], c.house["jupiter"]) == (10, 11, 1) else None


def _d_lords_moon(c: Ctx) -> str | None:
    moon = c.sign["moon"]
    in_k = [h for h in (11, 9, 2) if house_from(moon, c.sign[c.lord(h)]) in KENDRA]
    owns = [h for h in (2, 5, 11) if c.lord(h) == "jupiter"]
    return f"the lord of the {_o(in_k[0])} is in a kendra from the Moon and Jupiter rules the {_o(owns[0])}" if in_k and owns else None


DETECTORS: dict[str, Detect] = {
    "three_strong_kendras": _d_three_strong, "one_strong_retrograde": _d_retro, "digbala": _d_digbala, "vargottama_lagna_moon": _d_varg_lm,
    "vargottama_lagna_lord": _d_varg_ll, "full_moon_aspected": _d_full_aspected, "full_moon_kendra": _d_full_kendra, "venus_ashwini": _d_venus_ashwini,
    "lagna_lord_second": _d_ll_second, "mars_cardinal_lagna": _d_mars_cardinal, "ninth_tenth_exchange": _d_exchange, "sun_moon_sagittarius": _d_sun_moon_sag,
    "moon_leo_navamsa": _d_moon_leo_nav, "moon_three_own_navamsa": _d_three_own_nav, "vargottama_moon": _d_varg_moon, "full_vargottama_moon": _d_full_varg,
    "jupiter_moon_kendra": _d_jm_kendra, "moon_water_sign": _d_water, "venus_jupiter_aspect": _d_venus_jup, "jupiter_lagna": _d_jup_lagna,
    "lagna_lord_kendra": _d_ll_kendra, "mercury_kendra_jupiter": _d_merc, "exalted_with_friend_aspect": _d_exalted_friend,
    "sun_own_navamsa_moon_own_sign": _d_sun_moon_nav, "moon_pisces_full": _d_moon_pisces, "moon_exalted_full": _d_moon_exalted,
    "moon_adhimitra_venus": _d_adhimitra_venus, "moon_adhimitra_jupiter": _d_adhimitra_jupiter, "four_in_one_sign": _d_four_one_sign, "moon_saturn_decanate": _d_moon_sat_dec,
    "moon_mars_navamsa_saturn": _d_moon_mars_nav, "moon_sign_lord_saturn": _d_moon_lord_sat, "tenth_lord_four": _d_tenth_four,
    "malefics_3_6_11": _d_m36, "mars_mercury_second": _d_mm, "sun_venus_fourth": _d_sv, "mars_saturn_jupiter": _d_msj, "lords_from_moon": _d_lords_moon,
}
NB_KEYS = ("sign_or_exaltation_lord_kendra", "mutual_kendras", "aspected_by_sign_lord", "planet_in_kendra")


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> RajaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    if set(raw["yogas"]) != set(DETECTORS):
        raise ValueError(f"{path.name}: yogas {sorted(set(raw['yogas']) ^ set(DETECTORS))} do not match the code")
    for k, y in raw["yogas"].items():
        if not all(isinstance(y.get(f), str) and y[f].strip() for f in ("verse", "definition", "text")):
            raise ValueError(f"{path.name} {k}: needs verse, definition and text")
    if set(raw["neechabhanga"]["conditions"]) != set(NB_KEYS):
        raise ValueError(f"{path.name}: neechabhanga conditions must be {NB_KEYS}")
    return RajaRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")), raw["frame"], raw["yogas"], raw["neechabhanga"])


def find(rules: RajaRules, chart: Chart) -> tuple[Found, ...]:
    """The chapter 7 raja yogas and Neechabhanga cancellations in this chart. Empty until the rules are checked."""
    if not rules.servable:
        return ()
    c = Ctx(chart)
    out = []
    for key, y in rules.yogas.items():
        detail = DETECTORS[key](c)
        if detail:
            text = y["text"]
            if key == "four_in_one_sign":
                top = detail.split("the strongest there: ")[1].split(", ")
                text += ": " + "; ".join(f"{p.lower()} gives {y['orders'][p.lower()]}" for p in top)
            out.append(Found(key, y["verse"], text, detail))
    moon = c.sign["moon"]
    nb = rules.nb
    for p in SEVEN:
        if c.stand(p) != "depression":
            continue
        s = c.sign[p]
        sign_lord = SIGN_LORDS[s]
        exalted_here = next((q for q in SEVEN if c.ch20.exaltation[q] == s), None)
        exalt_lord = SIGN_LORDS[c.ch20.exaltation[p]]
        why = []
        for who in {sign_lord, exalted_here} - {None, p}:
            if house_from(c.lagna, c.sign[who]) in KENDRA or house_from(moon, c.sign[who]) in KENDRA:
                why.append(f"{who.title()}, {'lord of that sign' if who == sign_lord else 'the planet exalted in it'}, is in a kendra from the lagna or the Moon")
        if sign_lord != exalt_lord and house_from(c.sign[sign_lord], c.sign[exalt_lord]) in KENDRA:
            why.append(f"the lord of the debilitation sign ({sign_lord.title()}) and the lord of its exaltation sign ({exalt_lord.title()}) are in kendras from each other")
        if sign_lord != p and c.sees(sign_lord, s):
            why.append(f"{sign_lord.title()}, lord of the sign, aspects it")
        if house_from(c.lagna, s) in KENDRA or house_from(moon, s) in KENDRA:
            why.append("it is itself in a kendra from the lagna or the Moon")
        if why:
            out.append(Found("neechabhanga", nb["verse"], nb["text"], f"{p.title()} is debilitated in {SIGNS[s]}; " + "; ".join(dict.fromkeys(why))))
    return tuple(out)
