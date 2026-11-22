"""Brihat Jataka chapter XIII: the lunar yogas, found from a chart and read from the text.

Texts come from data/rules/brihat-jataka-chandra-yogas.yaml (quoted from the public-domain translation). This module loads
and validates it and decides which yogas the chart has; nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .vedic import house_from, sign_index

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-chandra-yogas.yaml"
_NEEDED = (
    "moon_from_sun",
    "adhi",
    "sunapha",
    "anapha",
    "durudhura",
    "kemadruma",
    "yoga_planet",
    "upachaya",
)


@dataclass(frozen=True)
class ChandraRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    raw: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    name: str  # "Moon from the Sun", "Adhi yoga", "Sunapha yoga", ...
    verse: str
    text: str  # quoted
    detail: str = ""  # which planets or houses made it so (computed from the chart)
    extra: tuple[str, ...] = ()  # further quoted conditions that apply to it


@dataclass(frozen=True)
class Yogas:
    found: tuple[Found, ...]
    checked: bool


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> ChandraRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    missing = [k for k in _NEEDED if k not in raw]
    if missing:
        raise ValueError(f"{path.name}: missing {missing}")
    m = raw["moon_from_sun"]
    if sorted(m["poor"] + m["moderate"] + m["excellent"]) != list(range(1, 13)):
        raise ValueError(
            f"{path.name}: moon_from_sun must split the twelve houses between poor, moderate and excellent"
        )
    for key in ("sunapha", "anapha", "durudhura", "kemadruma"):
        if not raw[key].get("text"):
            raise ValueError(f"{path.name}: {key} needs a text")
    if set(raw["planets"]) != {"mars", "mercury", "jupiter", "venus", "saturn"}:
        raise ValueError(f"{path.name}: the yoga planets are the five from Mars to Saturn")
    if not set(raw["planets"]) <= set(raw["yoga_planet"]):
        raise ValueError(f"{path.name}: yoga_planet needs a text for each of the five")
    return ChandraRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw,
    )


def find(rules: ChandraRules, chart: Chart) -> Yogas:
    """The lunar yogas this chart has. Empty until the rules are checked."""
    if not rules.servable:
        return Yogas((), False)
    r = rules.raw
    sign = {p: sign_index(pl.longitude) for p, pl in chart.planets.items()}
    lagna = sign_index(chart.ascendant)
    from_moon = {p: house_from(sign["moon"], sign[p]) for p in sign}
    out: list[Found] = []

    # Verse 1: the Moon's house from the Sun
    m = r["moon_from_sun"]
    h = house_from(sign["sun"], sign["moon"])
    grade = "poor" if h in m["poor"] else "moderate" if h in m["moderate"] else "excellent"
    out.append(
        Found(
            "The Moon from the Sun",
            m["verse"],
            m["text"],
            f"the Moon is in the {_ord(h)} house from the Sun: {grade}",
        )
    )

    # Verse 2: Adhi yoga
    a = r["adhi"]
    occupying = [p for p in a["planets"] if from_moon[p] in a["houses"]]
    if occupying:
        where = ", ".join(f"{p.title()} in the {_ord(from_moon[p])}" for p in occupying)
        out.append(
            Found(
                "Adhi yoga",
                a["verse"],
                a["text"],
                f"{where} from the Moon",
                (a["note"],),
            )
        )

    # Verses 3, 5-8: Sunapha, Anapha, Durudhura, Kemadruma, then the yoga planets
    second = [p for p in r["planets"] if from_moon[p] == 2]
    twelfth = [p for p in r["planets"] if from_moon[p] == 12]
    if second and twelfth:
        name, spec = "Durudhura yoga", r["durudhura"]
        detail = f"{', '.join(p.title() for p in second)} in the 2nd and {', '.join(p.title() for p in twelfth)} in the 12th from the Moon"
    elif second:
        name, spec, detail = (
            "Sunapha yoga",
            r["sunapha"],
            f"{', '.join(p.title() for p in second)} in the 2nd from the Moon",
        )
    elif twelfth:
        name, spec, detail = (
            "Anapha yoga",
            r["anapha"],
            f"{', '.join(p.title() for p in twelfth)} in the 12th from the Moon",
        )
    else:
        name, spec = "Kemadruma yoga", r["kemadruma"]
        with_moon = [p for p in sign if p != "moon" and sign[p] == sign["moon"]]
        in_kendra = house_from(lagna, sign["moon"]) in (1, 4, 7, 10)
        detail = (
            "no planet from Mars to Saturn in the 2nd or 12th from the Moon; the Moon is "
            f"{'in' if in_kendra else 'not in'} a kendra from the ascendant and "
            f"{'is with ' + ', '.join(p.title() for p in with_moon) if with_moon else 'has no planet with her'}"
        )
    extra = ()
    if name == "Kemadruma yoga":
        extra = (spec["cancelled_by_some"],)
    out.append(Found(name, spec["verse"], spec["text"], detail, extra))
    if name != "Kemadruma yoga":
        yp = r["yoga_planet"]
        for p in dict.fromkeys([*second, *twelfth]):
            out.append(
                Found(
                    f"The yoga planet {p.title()}",
                    yp["verse"],
                    yp[p],
                    "",
                    (yp["note"],) if len(set(second + twelfth)) > 1 else (),
                )
            )

    # Verse 9: benefics in the upachaya houses, from the lagna and from the Moon
    u = r["upachaya"]
    from_lagna_n = sum(1 for p in u["planets"] if house_from(lagna, sign[p]) in u["houses"])
    from_moon_n = sum(1 for p in u["planets"] if from_moon[p] in u["houses"])
    texts = []
    if from_lagna_n:
        texts.append(f"from the ascendant: {u['from_lagna'][from_lagna_n]}")
    if from_moon_n:
        texts.append(f"from the Moon: {u['from_moon'][from_moon_n]}")
    if texts:
        both = (u["both"],) if from_lagna_n and from_moon_n else ()
        out.append(
            Found(
                "Benefics in the upachaya houses",
                u["verse"],
                "; ".join(texts),
                f"{from_lagna_n} of Mercury, Jupiter and Venus in the 3rd, 6th, 10th or 11th from the ascendant, "
                f"{from_moon_n} from the Moon",
                (*both, u["overrules"]),
            )
        )
    return Yogas(tuple(out), True)


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
