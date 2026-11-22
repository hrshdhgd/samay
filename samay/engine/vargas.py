"""Brihat Jataka chapter XXI: what the planets' dignity in signs, horas, drekkanas, the rising navamsa and the trimsamsas says of a person.

Texts are in data/rules/brihat-jataka-vargas.yaml (quoted from the public-domain translation). This module codes the conditions. Nothing is returned until a
person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import house_effects
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import (
    SIGN_LORDS,
    SIGNS,
    degree_in_sign,
    house_from,
    navamsa_sign,
    sign_index,
)

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-vargas.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
MALEFICS = ("sun", "mars", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
TRIMSAMSA_PLANETS = ("mars", "saturn", "jupiter", "mercury", "venus")
FULL_ASPECTS = {
    "mars": (4, 7, 8),
    "jupiter": (5, 7, 9),
    "saturn": (3, 7, 10),
}  # Brihat Jataka II.13; every other body the 7th
KINDS = ("sarpa", "ayudha", "chatushpad", "pakshi")


@dataclass(frozen=True)
class VargaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    caution: str
    raw: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Finding:
    verse: str
    because: str  # what the chart shows, in plain words
    text: str  # quoted
    note: str = ""


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> VargaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    for key in ("own_signs", "friendly_signs", "weak_signs"):
        counts = raw[key]["counts"]
        if set(counts) != set(range(1, 8)) or not all(
            isinstance(t, str) and t.strip() for t in counts.values()
        ):
            raise ValueError(f"{path.name} {key}: needs a text for each count 1-7")
    if set(raw["moon_drekkana"]["kinds"]) != set(KINDS):
        raise ValueError(f"{path.name}: moon_drekkana needs the kinds {KINDS}")
    if [k for k in raw["rising_navamsa"] if k not in ("verse", "vargottama")] != SIGNS:
        raise ValueError(f"{path.name} rising_navamsa: needs the twelve signs, Aries first")
    if set(raw["trimsamsa_own"]) != set(TRIMSAMSA_PLANETS) or set(raw["trimsamsa_lights"]) - {"verse"} != set(
        TRIMSAMSA_PLANETS
    ):
        raise ValueError(f"{path.name}: trimsamsa rows need Mars, Saturn, Jupiter, Mercury and Venus")
    return VargaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["caution"],
        raw,
    )


def hora(lon: float) -> str:
    """'solar' or 'lunar': odd signs (Aries, Gemini...) run solar then lunar in their two 15-degree horas, even signs lunar then solar (Brihat Jataka I.11)."""
    odd, first = sign_index(lon) % 2 == 0, degree_in_sign(lon) < 15.0
    return "solar" if odd == first else "lunar"


def drekkana(lon: float) -> tuple[int, int]:
    """(the drekkana's sign, 1-3): the lords of a sign's three drekkanas are those of the sign, the 5th and the 9th from it (I.11)."""
    n = int(degree_in_sign(lon) // 10.0)
    return (sign_index(lon) + 4 * n) % 12, n + 1


def trimsamsa_lord(lon: float) -> str:
    """Odd signs: Mars 5, Saturn 5, Jupiter 8, Mercury 7, Venus 5 degrees; even signs the same in reverse (I.7)."""
    d = degree_in_sign(lon)
    order = (("mars", 5), ("saturn", 5), ("jupiter", 8), ("mercury", 7), ("venus", 5))
    if sign_index(lon) % 2 == 1:
        order = tuple(reversed(order))
    edge = 0.0
    for p, width in order:
        edge += width
        if d < edge:
            return p
    return order[-1][0]


def _aspects(by: str, by_sign: int, target_sign: int) -> bool:
    return house_from(by_sign, target_sign) in FULL_ASPECTS.get(by, (7,))


def _is_friend(ch20, a: str, b: str) -> bool:
    return b in ch20.friends[a]


def _group_hora(
    lons: dict[str, float], planets: tuple[str, ...], good_hora: str, good_odd: bool
) -> str | None:
    """'full' when every planet is in the stated hora of the stated kind of sign, 'moderate' when every planet is in the stated hora or every planet in the stated kind of
    sign (the translator's reading of 21.5), else None."""
    pairs = [(hora(lons[p]) == good_hora, (sign_index(lons[p]) % 2 == 0) == good_odd) for p in planets]
    if all(h and s for h, s in pairs):
        return "full"
    if all(h for h, _ in pairs) or all(s for _, s in pairs):
        return "moderate"
    return None


def find(rules: VargaRules, chart: Chart) -> tuple[Finding, ...] | None:
    """The chapter XXI statements that hold for this chart. None until the rules are checked."""
    if not rules.servable:
        return None
    r = rules.raw
    ch20 = house_effects.load_rules()
    lon = {p: chart.planets[p].longitude for p in SEVEN}
    sign = {p: sign_index(x) for p, x in lon.items()}
    out: list[Finding] = []

    own = [p for p in SEVEN if SIGN_LORDS[sign[p]] == p]
    friendly = [p for p in SEVEN if house_effects.strength(ch20, p, sign[p]) == "friendly"]
    weak = [p for p in SEVEN if house_effects.strength(ch20, p, sign[p]) in ("inimical", "depression")]
    for key, label, names in (
        ("own_signs", "in their own signs", own),
        ("friendly_signs", "in friendly signs", friendly),
        ("weak_signs", "in inimical or depression signs", weak),
    ):
        if names:
            out.append(
                Finding(
                    r[key]["verse"],
                    f"{len(names)} of the seven planets {label} ({', '.join(n.title() for n in names)})",
                    r[key]["counts"][len(names)],
                )
            )

    exalted = [p for p in SEVEN if house_effects.strength(ch20, p, sign[p]) == "exaltation"]
    if len(exalted) == 1:
        p = exalted[0]
        friends = [q for q in SEVEN if q != p and _is_friend(ch20, p, q) and _aspects(q, sign[q], sign[p])]
        if friends:
            out.append(
                Finding(
                    r["exalted"]["verse"],
                    f"{p.title()} is in its exaltation sign and {', '.join(f.title() for f in friends)} (friendly) aspects it",
                    r["exalted"]["aspected"],
                )
            )
    for p in exalted:
        friends = [q for q in SEVEN if q != p and sign[q] == sign[p] and _is_friend(ch20, p, q)]
        if friends:
            out.append(
                Finding(
                    r["exalted"]["verse"],
                    f"{p.title()} is in its exaltation sign with {', '.join(f.title() for f in friends)} (friendly)",
                    r["exalted"]["accompanied"],
                )
            )

    lagna_lon = chart.ascendant
    if sign_index(lagna_lon) == 10:
        out.append(
            Finding(
                r["aquarius_lagna"]["verse"],
                "the rising sign is Aquarius",
                r["aquarius_lagna"]["text"],
            )
        )

    h = r["horas"]
    for names, good_hora, good_odd, key in (
        (MALEFICS, "solar", True, "malefic"),
        (BENEFICS, "lunar", False, "benefic"),
    ):
        got = _group_hora(lon, names, good_hora, good_odd)
        if got:
            where = ", ".join(f"{p.title()} {hora(lon[p])} hora of {SIGNS[sign[p]]}" for p in names)
            out.append(
                Finding(
                    h["verse"],
                    f"{where}",
                    h[key] + (" (in a moderate degree)" if got == "moderate" else ""),
                    h["note"] + ("" if got == "full" else " " + h["moderate"]),
                )
            )

    d = r["moon_drekkana"]
    d_sign, d_no = drekkana(lon["moon"])
    d_lord = SIGN_LORDS[d_sign]
    where = f"the Moon is in the {('1st', '2nd', '3rd')[d_no - 1]} drekkana of {SIGNS[sign['moon']]} (the drekkana of {SIGNS[d_sign]}, lord {d_lord.title()})"
    if d_lord == "moon" or _is_friend(ch20, "moon", d_lord):
        out.append(Finding(d["verse"], where, d["good"]))
    elif d_lord in ch20.neutrals["moon"]:
        out.append(Finding(d["verse"], where, d["good"], d["neutral"]))
    hits = [k for k in KINDS if d_no in d["kinds"][k]["where"].get(sign["moon"], [])]
    for k in hits:
        out.append(
            Finding(
                d["verse"],
                where,
                d["kinds"][k]["text"],
                d["several"] if len(hits) > 1 else "",
            )
        )

    nav = navamsa_sign(lagna_lon)
    n = r["rising_navamsa"]
    vargottama = nav == sign_index(lagna_lon)
    text = f"a person born when the rising navamsa is that of {SIGNS[nav]} will be {n[SIGNS[nav]]}"
    out.append(
        Finding(
            n["verse"],
            f"the rising navamsa is that of {SIGNS[nav]}"
            + (" (the same as the rising sign: vargottama)" if vargottama else ""),
            text,
            n["vargottama"] if vargottama else "",
        )
    )

    for p in TRIMSAMSA_PLANETS:
        if trimsamsa_lord(lon[p]) == p:
            row = r["trimsamsa_own"][p]
            out.append(Finding(row["verse"], f"{p.title()} is in its own trimsamsa", row["text"]))
    for light in ("sun", "moon"):
        lord = trimsamsa_lord(lon[light])
        if lord != light:
            out.append(
                Finding(
                    r["trimsamsa_lights"]["verse"],
                    f"the {light.title()} is in the trimsamsa of {lord.title()}",
                    r["trimsamsa_lights"][lord][light],
                )
            )
    return tuple(out)
