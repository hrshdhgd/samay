"""Brihat Jataka chapter XV: ascetic yogas. Texts and definitions in data/rules/brihat-jataka-ascetic.yaml (quoted); conditions coded here. Nothing is returned until checked."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import phaladeepika_raja, raja_yogas
from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .malefic_yogas import STANDING_RANK
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vedic import SIGN_LORDS, SIGNS, degree_in_sign

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-ascetic.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
STRONG = ("own", "moolatrikona", "exaltation")
IDS = (
    "order",
    "combust",
    "lord_aspects_saturn",
    "saturn_aspects_lord",
    "moon_saturn_drekkana",
    "author",
    "king_ascetic",
)


@dataclass(frozen=True)
class AsceticRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    orders: dict
    rules: dict[str, dict]
    raja_note: str

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    verse: str
    detail: str
    text: str
    note: str = ""


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> AsceticRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    rules = {r["id"]: r for r in raw["rules"]}
    if set(rules) != set(IDS) or len(rules) != len(raw["rules"]):
        raise ValueError(f"{path.name}: rule ids must be exactly {IDS}")
    if not all(
        isinstance(r.get(f), str) and r[f].strip()
        for r in rules.values()
        for f in ("verse", "text", "definition")
    ):
        raise ValueError(f"{path.name}: every rule needs verse, text and definition")
    if set(raw["orders"]) != set(SEVEN) or not all(
        o.get("name") and o.get("note") for o in raw["orders"].values()
    ):
        raise ValueError(
            f"{path.name}: orders needs a name and note for each of the seven planets"
        )
    return AsceticRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw["orders"],
        rules,
        raw["raja_note"],
    )


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def find(rules: AsceticRules, chart: Chart) -> tuple[Found, ...] | None:
    """The chapter XV statements that hold for this chart. None until the rules are checked."""
    if not rules.servable:
        return None
    c = Ctx(chart)
    r = rules.rules
    out: list[Found] = []
    n_raja = len(raja_yogas.find(raja_yogas.load_rules(), chart)) + len(
        phaladeepika_raja.find(phaladeepika_raja.load_rules(), chart)
    )

    for sign in range(12):
        group = [p for p in SEVEN if c.sign[p] == sign]
        if len(group) >= 4:
            best = max(STANDING_RANK[c.stand(p)] for p in group)
            top = [p for p in group if STANDING_RANK[c.stand(p)] == best]
            orders = "; ".join(
                f"{p.title()}: {rules.orders[p]['name']} ({rules.orders[p]['note']})"
                for p in top
            )
            out.append(
                Found(
                    r["order"]["verse"],
                    f"{_names(group)} are together in {SIGNS[sign]}; the most powerful: {orders}",
                    r["order"]["text"],
                )
            )
            comb = [p for p in top if c.combust(p)]
            if comb:
                out.append(
                    Found(
                        r["combust"]["verse"],
                        f"{_names(comb)}, the most powerful, is combust",
                        r["combust"]["text"],
                    )
                )

    lord = SIGN_LORDS[c.sign["moon"]]
    if lord != "saturn":
        ls = c.sign[lord]
        if c.sees(lord, c.sign["saturn"]) and not [
            p for p in c.seers(ls) if p != "saturn" and p != lord
        ]:
            out.append(
                Found(
                    r["lord_aspects_saturn"]["verse"],
                    f"{lord.title()}, lord of the Moon's sign, aspects Saturn and only Saturn may aspect it",
                    r["lord_aspects_saturn"]["text"],
                )
            )
        if c.sees("saturn", ls) and c.stand(lord) not in STRONG:
            out.append(
                Found(
                    r["saturn_aspects_lord"]["verse"],
                    f"Saturn aspects {lord.title()}, lord of the Moon's sign, which is not powerful",
                    r["saturn_aspects_lord"]["text"],
                )
            )
    m = c.sign["moon"]
    dlord = SIGN_LORDS[
        (m + 4 * int(degree_in_sign(chart.planets["moon"].longitude) // 10.0)) % 12
    ]
    others = [p for p in c.seers(m) if p != "saturn"]
    if (
        dlord == "saturn"
        and SIGN_LORDS[c.nav["moon"]] in ("saturn", "mars")
        and c.sees("saturn", m)
        and not others
    ):
        out.append(
            Found(
                r["moon_saturn_drekkana"]["verse"],
                "the Moon is in a drekkana of Saturn and a navamsa of Saturn or Mars, aspected by Saturn alone",
                r["moon_saturn_drekkana"]["text"],
            )
        )

    if n_raja:
        if c.house["jupiter"] == 9 and all(
            c.sees("saturn", s) for s in (c.sign["jupiter"], c.sign["moon"], c.lagna)
        ):
            out.append(
                Found(
                    r["author"]["verse"],
                    f"Saturn aspects Jupiter, the Moon and the lagna; Jupiter is in the 9th; {n_raja} raja yoga(s)",
                    r["author"]["text"],
                    rules.raja_note,
                )
            )
        if c.house["saturn"] == 9 and not c.seers(c.sign["saturn"]):
            out.append(
                Found(
                    r["king_ascetic"]["verse"],
                    f"Saturn is in the 9th with no aspect on it; {n_raja} raja yoga(s)",
                    r["king_ascetic"]["text"],
                    rules.raja_note,
                )
            )
    return tuple(out)
