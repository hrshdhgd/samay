"""Brihat Jataka chapter XXIV: the book's pointers for a woman's chart (character, husband, marriage, children), the second source of chart:women.

Texts are in data/rules/brihat-jataka-women.yaml (quoted from the public-domain translation); conditions are coded here, one detector per rule id. SENSITIVE: the bot shows it
only after a warning and a tap. Nothing is returned until a person has checked the file.
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
from .vargas import trimsamsa_lord
from .vedic import SIGN_LORDS, SIGNS, navamsa_sign

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-women.yaml"
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
STRONG = ("own", "moolatrikona", "exaltation")
WEAK = ("inimical", "depression")
MOVABLE, FIXED = {0, 3, 6, 9}, {1, 4, 7, 10}
TRIM_LORDS = ("mars", "saturn", "jupiter", "mercury", "venus")


@dataclass(frozen=True)
class WomenBJRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    houses: dict
    closing: dict
    trimsamsa: dict
    setting: dict
    rules: dict[str, dict]

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Pointer:
    id: str
    verse: str
    detail: str  # what the chart shows
    text: str  # quoted


Detect = Callable[[Ctx], "str | tuple[str, str] | None"]


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def _refs(c: Ctx) -> list[tuple[str, int]]:
    """The 7th sign from the lagna and from the Moon's sign (once, if they are the same sign)."""
    out = [("the lagna", (c.lagna + 6) % 12)]
    moon7 = (c.sign["moon"] + 6) % 12
    return out if moon7 == out[0][1] else [*out, ("the Moon", moon7)]


def _in(c: Ctx, sign: int, among=MALEFICS + BENEFICS + ("moon",)) -> list[str]:
    return [p for p in among if c.sign[p] == sign]


def _weak(c: Ctx, sign: int) -> bool:
    lord = SIGN_LORDS[sign]
    return c.stand(lord) in WEAK or c.house[lord] in (6, 8, 12)


def _aspected_by(c: Ctx, sign: int, among) -> list[str]:
    return [p for p in among if c.sees(p, sign)]


def _each_seventh(test: Callable[[Ctx, int], str | None]) -> Detect:
    def d(c: Ctx) -> str | None:
        for label, s in _refs(c):
            got = test(c, s)
            if got:
                return f"the 7th from {label} ({SIGNS[s]}): {got}"
        return None
    return d


def _t_empty_weak(c: Ctx, s: int) -> str | None:
    return f"no planet in it, its lord {SIGN_LORDS[s].title()} is weak, no benefic aspects it" if not _in(c, s) and _weak(c, s) and not _aspected_by(c, s, BENEFICS) else None


def _t_in(planet: str, others=None) -> Callable[[Ctx, int], str | None]:
    def t(c: Ctx, s: int) -> str | None:
        if c.sign[planet] != s:
            return None
        if others is None:
            return f"{planet.title()} is in it"
        by = [p for p in _aspected_by(c, s, others) if p != planet]
        return f"{planet.title()} is in it, aspected by {_names(by)}" if by else None
    return t


def _t_several_malefics(c: Ctx, s: int) -> str | None:
    there = [p for p in MALEFICS if c.sign[p] == s]
    return f"{_names(there)} are in it" if len(there) >= 2 else None


def _t_mixed(c: Ctx, s: int) -> str | None:
    there = _in(c, s)
    return f"{_names(there)} are in it" if len(there) >= 2 and any(p in BENEFICS for p in there) and any(p in MALEFICS for p in there) else None


def _t_rejected_weak(c: Ctx, s: int) -> str | None:
    mal = [p for p in MALEFICS if c.sign[p] == s]
    ben = _aspected_by(c, s, BENEFICS)
    return f"{_names(mal)} is in it, its lord is weak and {_names(ben)} aspects it" if mal and _weak(c, s) and ben else None


def _d_signs(c: Ctx, parity: int | None) -> bool:
    return all(s % 2 == parity for s in (c.lagna, c.sign["moon"]))


def _d_feminine(c: Ctx) -> str | None:
    return "the lagna and the Moon's sign are both even signs" if _d_signs(c, 1) else None


def _d_virtuous(c: Ctx) -> str | None:
    both = [c.lagna, c.sign["moon"]]
    if _d_signs(c, 1) and all(_aspected_by(c, s, BENEFICS) for s in both):
        return "both even signs are aspected by benefics"
    return None


def _d_masculine(c: Ctx) -> str | None:
    return "the lagna and the Moon's sign are both odd signs" if _d_signs(c, 0) else None


def _d_mixed_character(c: Ctx) -> str | None:
    return "one of the lagna and the Moon's sign is odd and the other even" if c.lagna % 2 != c.sign["moon"] % 2 else None


def _d_wicked(c: Ctx) -> str | None:
    def touched(s: int) -> list[str]:
        return [p for p in MALEFICS if c.sign[p] == s or c.sees(p, s)]
    a, b = touched(c.lagna), touched(c.sign["moon"])
    return f"both the lagna sign and the Moon's sign are occupied or aspected by malefics ({_names(dict.fromkeys(a + b))})" if a and b else None


def _d_women_together(c: Ctx) -> str | None:
    sat_nav, ven_nav = c.nav["saturn"], c.nav["venus"]
    mutual = SIGN_LORDS[sat_nav] == "venus" and SIGN_LORDS[ven_nav] == "saturn" and c.sees("saturn", c.sign["venus"]) and c.sees("venus", c.sign["saturn"])
    if mutual:
        return "Saturn and Venus are in each other's navamsa and aspect each other"
    if c.lagna in (1, 6) and navamsa_sign(c.chart.ascendant) == 10:
        return f"the lagna is {SIGNS[c.lagna]} and the rising navamsa is that of Aquarius"
    return None


def _d_venus_mars_navamsas(c: Ctx) -> str | None:
    return "Venus and Mars are in each other's navamsa" if SIGN_LORDS[c.nav["venus"]] == "mars" and SIGN_LORDS[c.nav["mars"]] == "venus" else None


def _d_permitted(c: Ctx) -> str | None:
    s7 = (c.lagna + 6) % 12
    return "the Moon, Venus and Mars are all in the 7th from the lagna" if all(c.sign[p] == s7 for p in ("moon", "venus", "mars")) else None


def _d_mother_too(c: Ctx) -> str | None:
    by = _aspected_by(c, c.lagna, MALEFICS)
    if c.lagna in (9, 10, 0, 7) and c.sign["moon"] == c.lagna == c.sign["venus"] and by:
        return f"the lagna is {SIGNS[c.lagna]} with the Moon and Venus in it, aspected by {_names(by)}"
    return None


def _setting_nav(c: Ctx) -> int:
    return navamsa_sign((c.chart.ascendant + 180.0) % 360.0)


def _d_diseased(c: Ctx) -> str | None:
    n = _setting_nav(c)
    return f"the setting navamsa is {SIGNS[n]} and Saturn aspects the 7th" if SIGN_LORDS[n] == "mars" and c.sees("saturn", (c.lagna + 6) % 12) else None


def _d_fine(c: Ctx) -> str | None:
    n = _setting_nav(c)
    return f"the setting navamsa is {SIGNS[n]}, a navamsa of {SIGN_LORDS[n].title()}" if SIGN_LORDS[n] in BENEFICS else None


def _lagna_group(*names: str) -> Detect:
    need = set(names)
    return lambda c: f"{_names(names)} are in the lagna sign ({SIGNS[c.lagna]})" if all(c.sign[p] == c.lagna for p in need) else None


def _d_three(c: Ctx) -> str | None:
    for trio in (("moon", "mercury", "venus"), ("mercury", "jupiter", "venus")):
        if all(c.sign[p] == c.lagna for p in trio):
            return f"{_names(trio)} are in the lagna sign"
    return None


def _d_widow_eighth(c: Ctx) -> tuple[str, str] | None:
    s8 = (c.lagna + 7) % 12
    mal = [p for p in MALEFICS if c.sign[p] == s8]
    if not mal:
        return None
    lord8 = SIGN_LORDS[s8]
    antar = SIGN_LORDS[c.nav[lord8]]
    return (f"{_names(mal)} in the 8th ({SIGNS[s8]}); its lord {lord8.title()} is in the navamsa of {SIGNS[c.nav[lord8]]}, so the antardasha of {antar.title()}",
            f"the woman will become a widow, and the widowhood will occur in the antardasha of {antar.title()}, the planet whose navamsa the lord of the 8th occupies")


def _d_dies_first(c: Ctx) -> str | None:
    s8, s2 = (c.lagna + 7) % 12, (c.lagna + 1) % 12
    mal = [p for p in MALEFICS if c.sign[p] == s8]
    ben = [p for p in BENEFICS if c.sign[p] == s2]
    return f"{_names(mal)} in the 8th and {_names(ben)} in the 2nd" if mal and ben else None


def _d_few_sons(c: Ctx) -> str | None:
    return f"the Moon is in {SIGNS[c.sign['moon']]}" if c.sign["moon"] in (5, 7, 1, 4) else None


def _d_masculine_planets(c: Ctx) -> str | None:
    if c.lagna % 2 == 0 and c.stand("saturn") in ("friendly", "neutral") and all(c.stand(p) in WEAK for p in ("moon", "venus", "mercury")) \
            and all(c.stand(p) in STRONG for p in ("sun", "mars", "jupiter")):
        return "Saturn is middling, the Moon, Venus and Mercury are weak, the Sun, Mars and Jupiter strong, and the lagna is odd"
    return None


def _d_famed(c: Ctx) -> str | None:
    return "Jupiter, Mars, Venus and Mercury are strong and the lagna is even" if c.lagna % 2 == 1 and all(c.stand(p) in STRONG for p in ("jupiter", "mars", "venus", "mercury")) else None


def _d_ascetic(c: Ctx) -> tuple[str, str] | None:
    s7, s9 = (c.lagna + 6) % 12, (c.lagna + 8) % 12
    if not any(c.sign[p] == s7 for p in MALEFICS):
        return None
    ninth = _in(c, s9)
    if not ninth:
        return None
    return (f"a malefic in the 7th and {_names(ninth)} in the 9th",
            f"the woman will without doubt become an ascetic of the class belonging to {_names(ninth)}, the planet in the 9th house")


DETECTORS: dict[str, Detect] = {
    "feminine": _d_feminine, "virtuous": _d_virtuous, "masculine_shape": _d_masculine, "mixed_character": _d_mixed_character, "wicked": _d_wicked,
    "women_together": _d_women_together,
    "husband_wicked": _each_seventh(_t_empty_weak), "husband_hermaphrodite": _each_seventh(_t_in("mercury")),
    "husband_travels": _each_seventh(lambda c, s: SIGNS[s] if s in MOVABLE else None),
    "husband_stays": _each_seventh(lambda c, s: SIGNS[s] if s in FIXED else None),
    "husband_returns": _each_seventh(lambda c, s: SIGNS[s] if s not in MOVABLE | FIXED else None),
    "rejected_sun": _each_seventh(_t_in("sun")), "widow_young": _each_seventh(_t_in("mars", ("sun", "saturn"))),
    "unmarried_old": _each_seventh(_t_in("saturn", ("sun", "mars"))),
    "widow_malefics": _each_seventh(_t_several_malefics), "quits_husband": _each_seventh(_t_mixed), "rejected_weak": _each_seventh(_t_rejected_weak),
    "venus_mars_navamsas": _d_venus_mars_navamsas, "permitted": _d_permitted, "mother_too": _d_mother_too,
    "diseased_genital": _d_diseased, "fine_genital": _d_fine,
    "moon_venus_lagna": _lagna_group("moon", "venus"), "moon_mercury_lagna": _lagna_group("moon", "mercury"), "venus_mercury_lagna": _lagna_group("venus", "mercury"),
    "three_in_lagna": _d_three, "widow_eighth": _d_widow_eighth, "dies_first": _d_dies_first, "few_sons": _d_few_sons,
    "masculine_planets": _d_masculine_planets, "famed": _d_famed, "ascetic": _d_ascetic,
}


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> WomenBJRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rules = {r["id"]: r for r in raw["rules"]}
    if len(rules) != len(raw["rules"]) or set(rules) != set(DETECTORS):
        raise ValueError(f"{path.name}: the rule ids must be exactly those the engine codes")
    for r in rules.values():
        if not all(isinstance(r.get(f), str) and r[f].strip() for f in ("verse", "text", "definition")):
            raise ValueError(f"{path.name} {r.get('id')}: needs verse, text and definition")
    groups = raw["trimsamsa"]["groups"]
    if sorted(s for g in groups for s in g["signs"]) != sorted(SIGNS):
        raise ValueError(f"{path.name}: the trimsamsa groups must cover each of the twelve signs once")
    if not all(all(isinstance(g.get(p), str) and g[p] for p in TRIM_LORDS) for g in groups):
        raise ValueError(f"{path.name}: each trimsamsa group needs a text for Mars, Saturn, Jupiter, Mercury and Venus")
    if set(raw["setting"]) - {"verse"} != {"saturn", "mars", "venus", "mercury", "moon", "jupiter", "sun"}:
        raise ValueError(f"{path.name}: setting needs the seven planets")
    return WomenBJRules(v.get("level", "unchecked"), v.get("checked_by"), raw["edition"], str(raw.get("pages", "")), raw["frame"], raw["houses"], raw["closing"],
                        raw["trimsamsa"], raw["setting"], rules)


def _trimsamsa_pointers(rules: WomenBJRules, c: Ctx) -> list[Pointer]:
    """Verses 3-6: each of the rising trimsamsa and the Moon's trimsamsa, read with the sign it lies in; if both speak, the more powerful lord's comes to pass."""
    groups = {s: g for g in rules.trimsamsa["groups"] for s in g["signs"]}
    cands = []
    for label, lon, sign in (("the rising trimsamsa", c.chart.ascendant, c.lagna), ("the Moon's trimsamsa", c.chart.planets["moon"].longitude, c.sign["moon"])):
        lord = trimsamsa_lord(lon)
        g = groups[SIGNS[sign]]
        cands.append((label, lord, sign, g, STANDING_RANK[c.stand(lord)]))
    best = max(r for *_, r in cands)
    keep = cands if len({(lord, sign) for _, lord, sign, _, _ in cands}) == 1 or cands[0][4] == cands[1][4] else [x for x in cands if x[4] == best]
    out = []
    for label, lord, sign, g, _ in keep:
        note = f" ({rules.trimsamsa['more_powerful']['text']})" if len(cands) > len(keep) else ""
        out.append(Pointer(f"trimsamsa_{lord}", g["verse"], f"{label} is that of {lord.title()}, in {SIGNS[sign]}{note}", g[lord][:1].upper() + g[lord][1:]))
    return out


def _setting_pointers(rules: WomenBJRules, c: Ctx) -> list[Pointer]:
    sign, nav = (c.lagna + 6) % 12, _setting_nav(c)
    lords = [("sign", SIGN_LORDS[sign], sign), ("navamsa", SIGN_LORDS[nav], nav)]
    ranks = {x[1]: STANDING_RANK[c.stand(x[1])] for x in lords}
    if lords[0][1] != lords[1][1] and ranks[lords[0][1]] != ranks[lords[1][1]]:
        lords = [max(lords, key=lambda x: ranks[x[1]])]
    out = []
    for kind, lord, s in dict.fromkeys(lords):
        out.append(Pointer(f"setting_{lord}", rules.setting["verse"], f"the setting {kind} ({SIGNS[s]}) is that of {lord.title()}", rules.setting[lord][:1].upper() + rules.setting[lord][1:]))
    return out


def find(rules: WomenBJRules, chart: Chart) -> tuple[Pointer, ...] | None:
    """The chapter XXIV pointers that hold for this chart, in the book's order. None until the rules are checked."""
    if not rules.servable:
        return None
    c = Ctx(chart)
    out: list[Pointer] = []
    for rid, rule in rules.rules.items():
        if rid == "women_together":
            out += _trimsamsa_pointers(rules, c)
        got = DETECTORS[rid](c)
        if got is not None:
            detail, text = got if isinstance(got, tuple) else (got, rule["text"])
            out.append(Pointer(rid, rule["verse"], detail[:1].upper() + detail[1:], text))
        if rid == "fine_genital":
            out += _setting_pointers(rules, c)
    return tuple(out)
