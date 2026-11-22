"""Phaladeepika chapter 6: the yogas whose definition can be decided from a whole-sign chart.

Texts come from data/rules/phaladeepika-ch6-yogas.yaml (paraphrased). The definitions are coded here, each tied to the verse and to a
`definition` sentence in the YAML that a checker can compare with the book. Nothing is returned until the file has been checked.
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
from .vedic import SIGN_LORDS, SIGNS, house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "phaladeepika-ch6-yogas.yaml"
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
KENDRA, TRIKONA = {1, 4, 7, 10}, {1, 5, 9}
UPACHAYA, DUSTHANA = {3, 6, 10, 11}, {6, 8, 12}
FULL_ASPECTS = {
    "mars": (4, 7, 8),
    "jupiter": (5, 7, 9),
    "saturn": (3, 7, 10),
}  # houses counted from the planet (Brihat Jataka II.13)
MAHAPURUSHA = {  # planet -> (name, signs)
    "mars": ("ruchaka", {0, 7, 9}),
    "mercury": ("bhadra", {2, 5}),
    "jupiter": ("hamsa", {8, 11, 3}),
    "venus": ("malavya", {1, 6, 11}),
    "saturn": ("sasa", {9, 10, 6}),
}


@dataclass(frozen=True)
class YogaRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    yogas: dict[str, dict]
    sankhya: dict
    benefics: tuple[str, ...]
    malefics: tuple[str, ...]
    blemish_note: str

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    key: str
    name: str
    verse: str
    text: str
    detail: str


class Ctx:
    """The chart as the detectors need it: signs, houses from the lagna and the Moon, lords, strength."""

    def __init__(self, chart: Chart, rules: YogaRules):
        self.chart = chart
        self.rules = rules
        self.sign = {p: sign_index(chart.planets[p].longitude) for p in BODIES}
        self.lagna = sign_index(chart.ascendant)
        self.house = {p: house_from(self.lagna, s) for p, s in self.sign.items()}
        self.moon_house = {
            p: house_from(self.sign["moon"], s) for p, s in self.sign.items()
        }
        self._ch20 = house_effects.load_rules()

    def lord(self, house: int) -> str:
        return SIGN_LORDS[(self.lagna + house - 1) % 12]

    def standing(self, planet: str) -> str:
        return house_effects.strength(self._ch20, planet, self.sign[planet])

    def own_or_exalted(self, planet: str) -> bool:
        return self.standing(planet) in ("own", "moolatrikona", "exaltation")

    def own_friend_or_exalted(self, planet: str) -> bool:
        return self.standing(planet) in (
            "own",
            "moolatrikona",
            "exaltation",
            "friendly",
        )

    def aspects(self, by: str, target_sign: int) -> bool:
        """Full aspect: every planet the 7th; Mars the 4th and 8th, Jupiter the 5th and 9th, Saturn the 3rd and 10th."""
        return house_from(self.sign[by], target_sign) in FULL_ASPECTS.get(by, (7,))


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


Detail = (
    tuple[str, object] | None
)  # (detail sentence, optional key into the yoga's `texts`)


def _mahapurusha(planet: str) -> Callable[[Ctx], Detail]:
    _, signs = MAHAPURUSHA[planet]

    def detect(c: Ctx) -> Detail:
        if c.sign[planet] not in signs:
            return None
        refs = [
            name
            for name, h in (("lagna", c.house[planet]), ("Moon", c.moon_house[planet]))
            if h in KENDRA
        ]
        if not refs:
            return None
        return (
            f"{planet.title()} is in {SIGNS[c.sign[planet]]}, in a kendra from the {' and from the '.join(refs)}",
            None,
        )

    return detect


def _mahapurusha_count(c: Ctx) -> Detail:
    names = [MAHAPURUSHA[p][0] for p in MAHAPURUSHA if _mahapurusha(p)(c)]
    return (
        (f"{len(names)} of the five: {', '.join(n.title() for n in names)}", len(names))
        if names
        else None
    )


def _vesi_vasi(
    planets: tuple[str, ...], two: bool, twelve: bool
) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        sun = c.sign["sun"]
        in2 = [p for p in planets if c.sign[p] == (sun + 1) % 12]
        in12 = [p for p in planets if c.sign[p] == (sun - 1) % 12]
        if two and twelve and in2 and in12:
            return (
                f"{', '.join(p.title() for p in in2)} in the 2nd and {', '.join(p.title() for p in in12)} in the 12th from the Sun",
                None,
            )
        if two and not twelve and in2 and not in12:
            return f"{', '.join(p.title() for p in in2)} in the 2nd from the Sun", None
        if twelve and not two and in12 and not in2:
            return (
                f"{', '.join(p.title() for p in in12)} in the 12th from the Sun",
                None,
            )
        return None

    return detect


def _kartari(planets: tuple[str, ...]) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        in2 = [p for p in planets if c.house[p] == 2]
        in12 = [p for p in planets if c.house[p] == 12]
        return (
            (
                f"{', '.join(p.title() for p in in12)} in the 12th and {', '.join(p.title() for p in in2)} in the 2nd",
                None,
            )
            if in2 and in12
            else None
        )

    return detect


def _amala(c: Ctx) -> Detail:
    got = [
        f"{p.title()} in the 10th from the {ref}"
        for p in c.rules.benefics
        for ref, h in (("lagna", c.house[p]), ("Moon", c.moon_house[p]))
        if h == 10
    ]
    return ("; ".join(got), None) if got else None


def _vasumati(c: Ctx) -> Detail:
    for ref, houses in (("lagna", c.house), ("Moon", c.moon_house)):
        if all(houses[p] in UPACHAYA for p in c.rules.benefics):
            return (
                f"Mercury, Jupiter and Venus are all in upachaya houses from the {ref}",
                None,
            )
    return None


def _kesari(c: Ctx) -> Detail:
    h = house_from(c.sign["jupiter"], c.sign["moon"])
    return (f"the Moon is in the {_ord(h)} from Jupiter", None) if h in KENDRA else None


def _sakata(c: Ctx) -> Detail:
    h = house_from(c.sign["jupiter"], c.sign["moon"])
    return (
        (
            f"the Moon is in the {_ord(h)} from Jupiter, and not in a kendra from the lagna",
            None,
        )
        if h in DUSTHANA and c.house["moon"] not in KENDRA
        else None
    )


def _moon_from_sun(houses: set[int]) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        h = house_from(c.sign["sun"], c.sign["moon"])
        return (
            (f"the Moon is in the {_ord(h)} from the Sun", None)
            if h in houses
            else None
        )

    return detect


def _lakshmi(c: Ctx) -> Detail:
    ninth = c.lord(9)
    ok = all(
        c.own_or_exalted(p) and c.house[p] in KENDRA | TRIKONA for p in ("venus", ninth)
    )
    return (
        (
            f"Venus and the 9th lord {ninth.title()} are each in an own or exaltation sign, in a kendra or trikona",
            None,
        )
        if ok
        else None
    )


def _gouri(c: Ctx) -> Detail:
    ok = (
        c.own_or_exalted("moon")
        and c.house["moon"] in KENDRA | TRIKONA
        and c.aspects("jupiter", c.sign["moon"])
    )
    return (
        (
            "the Moon is in her own or exaltation sign, in a kendra or trikona, aspected by Jupiter",
            None,
        )
        if ok
        else None
    )


def _saraswati(c: Ctx) -> Detail:
    ok = all(
        c.house[p] in KENDRA | TRIKONA | {2} for p in c.rules.benefics
    ) and c.own_friend_or_exalted("jupiter")
    return (
        (
            "Mercury, Jupiter and Venus are in kendras, trikonas or the 2nd, and Jupiter is in an own, friend's or exaltation sign",
            None,
        )
        if ok
        else None
    )


def _trio(planets_or_houses: tuple[str | int, ...]) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        planets = [c.lord(x) if isinstance(x, int) else x for x in planets_or_houses]
        ok = all(
            c.own_friend_or_exalted(p) and c.house[p] in KENDRA | TRIKONA
            for p in planets
        )
        names = ", ".join(dict.fromkeys(p.title() for p in planets))
        return (
            (
                f"{names} each in an exaltation, own or friend's sign, in a kendra or trikona",
                None,
            )
            if ok
            else None
        )

    return detect


def _exchanges(kind: str) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        pairs = []
        for a in range(1, 13):
            for b in range(a + 1, 13):
                la, lb = c.lord(a), c.lord(b)
                if la == lb or c.house[la] != b or c.house[lb] != a:
                    continue
                tag = (
                    "dainya"
                    if {a, b} & DUSTHANA
                    else "kahala" if 3 in (a, b) else "maha"
                )
                if tag == kind:
                    pairs.append(
                        f"the {_ord(a)} lord {la.title()} in the {_ord(b)} and the {_ord(b)} lord {lb.title()} in the {_ord(a)}"
                    )
        return ("; ".join(pairs), None) if pairs else None

    return detect


def _raja(c: Ctx) -> Detail:
    l9, l10 = c.lord(9), c.lord(10)
    if l9 != l10 and c.sign[l9] == c.sign[l10] and c.house[l9] not in DUSTHANA:
        return (
            f"the 9th lord {l9.title()} and the 10th lord {l10.title()} are together in the {_ord(c.house[l9])} house",
            None,
        )
    return None


def _adhi(ref: str) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        houses = c.house if ref == "lagna" else c.moon_house
        if all(houses[p] in (6, 7, 8) for p in c.rules.benefics):
            return (
                f"Mercury, Jupiter and Venus are all in the 6th, 7th or 8th from the {ref}",
                None,
            )
        return None

    return detect


def _lord_in_dusthana(house: int) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        lord = c.lord(house)
        h = c.house[lord]
        return (
            (f"the {_ord(house)} lord {lord.title()} is in the {_ord(h)}", None)
            if h in DUSTHANA
            else None
        )

    return detect


def _vipareeta(into: int) -> Callable[[Ctx], Detail]:
    def detect(c: Ctx) -> Detail:
        got = [
            f"the {_ord(h)} lord {c.lord(h).title()}"
            for h in (6, 8, 12)
            if c.house[c.lord(h)] == into
        ]
        return (f"{' and '.join(got)} in the {_ord(into)}", None) if got else None

    return detect


DETECTORS: dict[str, Callable[[Ctx], Detail]] = {
    **{MAHAPURUSHA[p][0]: _mahapurusha(p) for p in MAHAPURUSHA},
    "mahapurusha_count": _mahapurusha_count,
    "subhavesi": _vesi_vasi(("mercury", "jupiter", "venus"), True, False),
    "subhavasi": _vesi_vasi(("mercury", "jupiter", "venus"), False, True),
    "subhobhayachari": _vesi_vasi(("mercury", "jupiter", "venus"), True, True),
    "papavesi": _vesi_vasi(("mars", "saturn"), True, False),
    "papavasi": _vesi_vasi(("mars", "saturn"), False, True),
    "papobhayachari": _vesi_vasi(("mars", "saturn"), True, True),
    "subhakartari": _kartari(("mercury", "jupiter", "venus")),
    "papakartari": _kartari(("sun", "mars", "saturn")),
    "amala": _amala,
    "vasumati": _vasumati,
    "kesari": _kesari,
    "sakata": _sakata,
    "varishtha": _moon_from_sun({3, 6, 9, 12}),
    "sama": _moon_from_sun({2, 5, 8, 11}),
    "adhama": _moon_from_sun(KENDRA),
    "lakshmi": _lakshmi,
    "gouri": _gouri,
    "saraswati": _saraswati,
    "srikantha": _trio((1, "sun", "moon")),
    "srinatha": _trio(("venus", 9, "mercury")),
    "virinchi": _trio(("jupiter", 5, "saturn")),
    "maha": _exchanges("maha"),
    "dainya": _exchanges("dainya"),
    "kahala": _exchanges("kahala"),
    "raja": _raja,
    "lagnadhi": _adhi("lagna"),
    "chandradhi": _adhi("Moon"),
    "ava": _lord_in_dusthana(1),
    "nisswa": _lord_in_dusthana(2),
    "mriti": _lord_in_dusthana(3),
    "kuhu": _lord_in_dusthana(4),
    "pamara": _lord_in_dusthana(5),
    "dushkriti": _lord_in_dusthana(7),
    "nirbhagya": _lord_in_dusthana(9),
    "duryoga": _lord_in_dusthana(10),
    "daridra": _lord_in_dusthana(11),
    "harsha": _vipareeta(6),
    "sarala": _vipareeta(8),
    "vimala": _vipareeta(12),
}


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> YogaRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    yogas = raw["yogas"]
    if set(yogas) != set(DETECTORS):
        raise ValueError(
            f"{path.name}: yogas {sorted(set(yogas) ^ set(DETECTORS))} have no matching definition in the code"
        )
    for key, y in yogas.items():
        if not all(
            isinstance(y.get(f), str) and y[f].strip()
            for f in ("name", "verse", "definition")
        ):
            raise ValueError(f"{path.name} {key}: needs name, verse and definition")
        if not (isinstance(y.get("text"), str) and y["text"].strip()) and not y.get(
            "texts"
        ):
            raise ValueError(f"{path.name} {key}: needs a text (or texts by key)")
    sk = raw["sankhya"]
    if set(sk["texts"]) != set(range(1, 8)) or any(n not in sk for n in range(1, 8)):
        raise ValueError(
            f"{path.name}: sankhya needs a name and a text for 1 to 7 signs"
        )
    return YogaRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        yogas,
        sk,
        tuple(raw["benefics"]),
        tuple(raw["malefics"]),
        raw["blemish_note"],
    )


def find(rules: YogaRules, chart: Chart) -> tuple[Found, ...]:
    """The chapter 6 yogas this chart has. Empty until the rules are checked."""
    if not rules.servable:
        return ()
    ctx = Ctx(chart, rules)
    out = []
    for key, y in rules.yogas.items():
        got = DETECTORS[key](ctx)
        if got is None:
            continue
        detail, text_key = got
        text = y["texts"][text_key] if y.get("texts") else y["text"]
        out.append(Found(key, y["name"], y["verse"], text.strip(), detail))
    # the Sankhya names Phaladeepika gives by the number of signs the seven planets occupy (verses 39-41)
    n = len({ctx.sign[p] for p in BODIES[:7]})
    out.append(
        Found(
            "sankhya",
            rules.sankhya[n]["name"] + " (by the number of signs)",
            rules.sankhya["verse"],
            rules.sankhya["texts"][n].strip(),
            f"the seven planets are in {n} sign{'s' if n > 1 else ''}",
        )
    )
    return tuple(out)
