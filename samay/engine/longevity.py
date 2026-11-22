"""Phaladeepika chapters 13 and 14: the book's rules for long and short life, dangers at birth, and the cause of death.

Texts come from data/rules/phaladeepika-ch13-14-longevity.yaml (paraphrased). Conditions are coded here. This is sensitive: the bot shows it only
after a warning and a tap. It never computes a date or a window for death; the book's transit rules for that (13.18-19) are left out on purpose.
Nothing is returned until the file has been checked by a person.
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

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch13-14-longevity.yaml"
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
SEVEN = BODIES[:7]
MALEFICS = ("sun", "mars", "saturn", "rahu", "ketu")
BENEFICS = ("mercury", "jupiter", "venus")
KENDRA, PANAPHARA, APOKLIMA = {1, 4, 7, 10}, {2, 5, 8, 11}, {3, 6, 9, 12}
FULL_ASPECTS = {
    "mars": (4, 7, 8),
    "jupiter": (5, 7, 9),
    "saturn": (3, 7, 10),
}  # Brihat Jataka II.13; every other body the 7th
RANK = {
    "exaltation": 6,
    "moolatrikona": 5,
    "own": 4,
    "friendly": 3,
    "neutral": 2,
    "inimical": 1,
    "depression": 0,
}
_REQUIRED = (
    "caution",
    "classes",
    "first_twelve",
    "gandanta",
    "moon_degrees",
    "lagna_degrees",
    "balarishta",
    "weak_lords",
    "kendra_rule",
    "friendship_rule",
    "stronger",
    "short_vicissitudes",
    "protections",
    "death_planets",
    "cause_rule",
    "death_signs",
    "manner",
)


@dataclass(frozen=True)
class LongevityRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    raw: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Item:
    verse: str
    text: str  # the book's statement (paraphrased)
    detail: str  # what in this chart made it apply


@dataclass(frozen=True)
class Longevity:
    caution: str
    framing: tuple[
        Item, ...
    ]  # the classes and the first-twelve-years note, always shown
    dangers: tuple[Item, ...]  # dangers at birth the chart meets
    class_signs: tuple[
        Item, ...
    ]  # the chart's pointers to a long, middle or short life
    protections: tuple[Item, ...]
    cause: tuple[Item, ...]  # the cause of death by the 8th house, and the manner
    cancelled: str  # the book's cancellation, shown when benefics stand in a kendra or aspect the lagna / Moon


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> LongevityRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise ValueError(f"{path.name}: missing {missing}")
    if [k for k in raw["death_signs"] if k != "verse"] != SIGNS or set(
        raw["death_planets"]
    ) - {"verse"} != set(BODIES):
        raise ValueError(f"{path.name}: needs the twelve signs and the nine planets")
    for key in ("moon_degrees", "lagna_degrees"):
        if len(raw[key]["values"]) != 12 or not all(
            1 <= d <= 30 for d in raw[key]["values"]
        ):
            raise ValueError(f"{path.name} {key}: twelve degrees from 1 to 30")
    if set(raw["balarishta"]["rules"]) != {
        "lagna_and_8th",
        "lagna_and_7th",
        "hemmed",
        "waning_dusthana",
        "waning_malefics",
        "malefics_7_8",
    }:
        raise ValueError(f"{path.name}: balarishta rules changed; update the engine")
    return LongevityRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw,
    )


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def find(rules: LongevityRules, chart: Chart) -> Longevity | None:
    """What the book's rules point to in this chart. None until the rules are checked."""
    if not rules.servable:
        return None
    r = rules.raw
    ch20 = house_effects.load_rules()
    lagna = sign_index(chart.ascendant)
    sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
    house = {p: house_from(lagna, s) for p, s in sign.items()}
    lord = {h: SIGN_LORDS[(lagna + h - 1) % 12] for h in range(1, 13)}
    waning = (
        chart.planets["moon"].longitude - chart.planets["sun"].longitude
    ) % 360.0 >= 180.0

    def stand(p: str) -> str:
        return house_effects.strength(ch20, p, sign[p])

    def weak(p: str) -> bool:
        return stand(p) in ("inimical", "depression") or house_effects.is_astangata(
            ch20, p, chart
        )

    def sees(by: str, target: int) -> bool:
        return (
            by in SEVEN
            and sign[by] != target
            and house_from(sign[by], target) in FULL_ASPECTS.get(by, (7,))
        )

    def with_(p: str, among: tuple[str, ...]) -> list[str]:
        return [q for q in among if q != p and sign[q] == sign[p]]

    item = lambda block, text, detail: Item(block["verse"], text, detail)

    framing = (
        Item(r["classes"]["verse"], r["classes"]["text"], ""),
        Item(r["first_twelve"]["verse"], r["first_twelve"]["text"], ""),
    )

    dangers: list[Item] = []
    g = r["gandanta"]
    for name, lon in (
        ("lagna", chart.ascendant),
        ("Moon", chart.planets["moon"].longitude),
    ):
        s, d = sign_index(lon), degree_in_sign(lon)
        if (s in g["signs_end"] and d >= 30 - 10 / 3) or (
            s in g["signs_start"] and d < 10 / 3
        ):
            edge = "end" if s in g["signs_end"] else "start"
            dangers.append(
                item(
                    g,
                    g["text"],
                    f"the {name} is in the {edge} of {SIGNS[s]}, within 3°20' of a sign junction",
                )
            )
    m = r["moon_degrees"]
    ms, md = sign["moon"], int(degree_in_sign(chart.planets["moon"].longitude)) + 1
    if md == m["values"][ms]:
        extra = (
            " and she is in a kendra or the 8th house"
            if house["moon"] in KENDRA | {8}
            else ""
        )
        dangers.append(
            item(
                m,
                m["text"],
                f"the Moon is in the {_ord(md)} degree of {SIGNS[ms]}{extra}",
            )
        )
    la = r["lagna_degrees"]
    ld = int(degree_in_sign(chart.ascendant)) + 1
    if ld == la["values"][lagna]:
        dangers.append(
            item(
                la,
                la["text"],
                f"the lagna is in the {_ord(ld)} degree of {SIGNS[lagna]}",
            )
        )

    bal = r["balarishta"]
    mal_in = lambda h: [p for p in MALEFICS if house[p] == h]
    found: list[tuple[str, str]] = []
    if mal_in(1) and mal_in(8):
        found.append(
            (
                "lagna_and_8th",
                f"{', '.join(p.title() for p in mal_in(1))} in the 1st and {', '.join(p.title() for p in mal_in(8))} in the 8th",
            )
        )
    if mal_in(1) and mal_in(7):
        found.append(
            (
                "lagna_and_7th",
                f"{', '.join(p.title() for p in mal_in(1))} in the 1st and {', '.join(p.title() for p in mal_in(7))} in the 7th",
            )
        )
    around = lambda s: any(sign[p] == (s - 1) % 12 for p in MALEFICS) and any(
        sign[p] == (s + 1) % 12 for p in MALEFICS
    )
    if around(sign["moon"]) and around(lagna):
        found.append(
            (
                "hemmed",
                "malefics stand in the sign before and the sign after both the Moon and the lagna",
            )
        )
    if waning and house["moon"] in (6, 8, 12):
        found.append(
            (
                "waning_dusthana",
                f"the waning Moon is in the {_ord(house['moon'])} house",
            )
        )
    if waning and house["moon"] in (1, 5, 7, 9) and with_("moon", MALEFICS):
        found.append(
            (
                "waning_malefics",
                f"the waning Moon is in the {_ord(house['moon'])} house with {', '.join(p.title() for p in with_('moon', MALEFICS))}",
            )
        )
    if mal_in(7) and mal_in(8):
        found.append(("malefics_7_8", "malefics in both the 7th and the 8th"))
    for key, detail in found:
        dangers.append(
            Item(
                bal["verse"],
                f"A child dies soon after birth with {bal['rules'][key]['text']}",
                detail,
            )
        )
    wl = r["weak_lords"]
    for who, p in (
        ("the lord of the lagna", lord[1]),
        ("the lord of the Moon's sign", SIGN_LORDS[sign["moon"]]),
    ):
        if weak(p) and house[p] in (6, 8, 12):
            dangers.append(
                item(
                    wl,
                    wl["text"],
                    f"{who} ({p.title()}) is weak and in the {_ord(house[p])} house, in {SIGNS[sign[p]]}, sign {sign[p] + 1}",
                )
            )

    cancel = ""
    if found or dangers:
        kendra_benefic = [p for p in BENEFICS if house[p] in KENDRA]
        sees_lagna = [p for p in BENEFICS if sees(p, lagna)]
        sees_moon = [p for p in BENEFICS if sees(p, sign["moon"])]
        why = []
        if kendra_benefic:
            why.append(f"{', '.join(p.title() for p in kendra_benefic)} in a kendra")
        if sees_lagna:
            why.append(
                f"{', '.join(p.title() for p in sees_lagna)} aspecting the lagna"
            )
        if sees_moon:
            why.append(f"{', '.join(p.title() for p in sees_moon)} aspecting the Moon")
        if why:
            cancel = f"{bal['cancelled']} In this chart: {'; '.join(why)}."

    classes: list[Item] = []
    kr = r["kendra_rule"]
    placed = lambda ps, hs: all(house[p] in hs for p in ps)
    ben = [lord[1], *BENEFICS]
    mal = [lord[8], "sun", "mars", "saturn"]
    for hs, label_b, label_m in (
        (KENDRA, "long", "short"),
        (PANAPHARA, "middle", "middle"),
        (APOKLIMA, "short", "long"),
    ):
        if placed(ben, hs):
            classes.append(
                Item(
                    kr["verse"],
                    f"The lord of the lagna and all the benefics are in {'kendras' if hs is KENDRA else 'panaphara houses' if hs is PANAPHARA else 'apoklima houses'}: a {label_b} life.",
                    f"{lord[1].title()}, Mercury, Jupiter and Venus",
                )
            )
        if placed(mal, hs):
            classes.append(
                Item(
                    kr["verse"],
                    f"The lord of the 8th and all the malefics are in {'kendras' if hs is KENDRA else 'panaphara houses' if hs is PANAPHARA else 'apoklima houses'}: a {label_m} life.",
                    f"{lord[8].title()}, Sun, Mars and Saturn",
                )
            )
    fr = r["friendship_rule"]
    pairs = [
        (SIGN_LORDS[sign["moon"]], SIGN_LORDS[(sign["moon"] + 7) % 12]),
        (lord[1], lord[8]),
        (lord[1], "sun"),
    ]
    kinds = []
    for a, b in pairs:
        if a == b:
            continue
        fa, fb = b in ch20.friends[a], a in ch20.friends[b]
        na, nb = b in ch20.neutrals[a], a in ch20.neutrals[b]
        kinds.append(
            "friends"
            if fa and fb
            else (
                "neutral"
                if na and nb
                else "enemies" if not (fa or na or fb or nb) else "mixed"
            )
        )
    if kinds and len(set(kinds)) == 1 and kinds[0] != "mixed":
        classes.append(
            Item(
                fr["verse"],
                fr["text"],
                f"all the pairs that apply are {kinds[0]}: "
                + "; ".join(f"{a.title()} and {b.title()}" for a, b in pairs if a != b),
            )
        )
    st = r["stronger"]
    nav_l = navamsa_sign(chart.ascendant)
    nav_m = navamsa_sign(chart.planets["moon"].longitude)

    def rank_in(p: str) -> int:
        return RANK[stand(p)]

    comps = [
        (lord[1], lord[8]),
        (SIGN_LORDS[nav_l], SIGN_LORDS[(nav_l + 7) % 12]),
        (SIGN_LORDS[sign["moon"]], SIGN_LORDS[(sign["moon"] + 7) % 12]),
        (SIGN_LORDS[nav_m], SIGN_LORDS[(nav_m + 7) % 12]),
    ]
    wins = [rank_in(a) > rank_in(b) for a, b in comps]
    if all(wins):
        classes.append(
            Item(
                st["verse"],
                st["text"],
                "in all four comparisons the first planet is the stronger by its standing in its sign",
            )
        )
    elif not any(rank_in(a) > rank_in(b) for a, b in comps):
        classes.append(
            Item(
                st["verse"],
                "In none of the four comparisons is the lord of the lagna side stronger, so the book says the reverse: "
                + st["text"].split("Otherwise")[0].strip(),
                "by standing in the sign; ties count as not stronger",
            )
        )
    sv = r["short_vicissitudes"]
    if (
        rank_in(lord[8]) > rank_in(lord[1])
        and house[lord[8]] in KENDRA
        and mal_in(8)
        and mal_in(12)
    ):
        classes.append(
            item(
                sv,
                sv["text"],
                f"the 8th lord {lord[8].title()} is stronger than the lagna lord, in a kendra, with malefics in the 8th and 12th",
            )
        )

    prot: list[Item] = []
    pr = r["protections"]
    ll = lord[1]
    if (
        house[ll] in KENDRA
        and stand(ll) in ("own", "moolatrikona", "exaltation")
        and not with_(ll, MALEFICS)
        and not any(sees(p, sign[ll]) for p in MALEFICS if p in SEVEN)
        and (with_(ll, BENEFICS) or any(sees(p, sign[ll]) for p in BENEFICS))
    ):
        prot.append(
            Item(
                pr["verse"],
                pr["lagna_lord"]["text"],
                f"the lagna lord {ll.title()} is in the {_ord(house[ll])}, in {stand(ll)} sign, with benefics and no malefics",
            )
        )
    if house["jupiter"] == 1 and stand("jupiter") in (
        "own",
        "moolatrikona",
        "exaltation",
    ):
        prot.append(
            Item(
                pr["verse"],
                pr["jupiter"]["text"],
                "Jupiter is in the lagna in a strong sign",
            )
        )
    if (
        not waning
        and house["moon"] in (1, 4, 5, 7, 9, 10, 11)
        and nav_m in (3, 4, 8, 11)
    ):
        prot.append(
            Item(
                pr["verse"],
                pr["bright_moon"]["text"],
                f"the Moon is waxing, in the {_ord(house['moon'])} house, in a {SIGNS[nav_m]} navamsa",
            )
        )

    cause: list[Item] = []
    dp = r["death_planets"]
    eighth = (lagna + 7) % 12
    on_8 = [p for p in BODIES if sign[p] == eighth]
    seeing = [p for p in SEVEN if sees(p, eighth) and p not in on_8]
    cand = on_8 + seeing
    if cand:
        best = max(RANK[stand(p)] if p in SEVEN else -1 for p in cand)
        top = [p for p in cand if (RANK[stand(p)] if p in SEVEN else -1) == best]
        for p in top:
            how = "in" if p in on_8 else "aspecting"
            cause.append(
                Item(
                    dp["verse"],
                    f"{p.title()}: {dp[p]}",
                    f"{p.title()} is {how} the 8th house and is the strongest there"
                    + (" (several are equally strong)" if len(top) > 1 else ""),
                )
            )
    else:
        cause.append(
            Item(
                r["death_signs"]["verse"],
                f"{SIGNS[eighth]}: {r['death_signs'][SIGNS[eighth]]}",
                "no planet is in or aspects the 8th house, so the book reads the 8th house's sign",
            )
        )
    mn = r["manner"]
    l12 = lord[12]
    benefic_sign = (
        SIGN_LORDS[sign[l12]] in BENEFICS
        or bool(with_(l12, BENEFICS))
        or (l12 in BENEFICS and any(house[p] == 12 for p in BENEFICS))
    )
    malefic_sign = (
        (SIGN_LORDS[sign[l12]] in MALEFICS and bool(with_(l12, MALEFICS)))
        or l12 in ("sun", "mars", "saturn")
        or any(house[p] == 12 for p in MALEFICS)
    )
    if benefic_sign:
        cause.append(
            Item(
                mn["verse"],
                mn["painless"],
                f"the 12th lord {l12.title()} is in a benefic's sign or with a benefic, or the 12th is owned and occupied by one",
            )
        )
    if malefic_sign:
        cause.append(
            Item(
                mn["verse"],
                mn["painful"],
                f"the 12th lord {l12.title()} is in a malefic's sign with a malefic, or the 12th is owned or occupied by a malefic",
            )
        )
    return Longevity(
        r["caution"],
        framing,
        tuple(dangers),
        tuple(classes),
        tuple(prot),
        tuple(cause),
        cancel,
    )
