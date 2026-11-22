"""Brihat Jataka chapter XXII: karaka (helping) planets, the yogas of a happy life, and when in a dasha its lord's effects fall.

Texts are in data/rules/brihat-jataka-miscellaneous.yaml (quoted from the public-domain translation). Nothing is returned until a person has checked the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .entries import SERVABLE_LEVELS
from .ephemeris import Chart
from .paths import DATA_DIR
from .phaladeepika_raja import Ctx
from .vedic import SIGN_LORDS, SIGNS, house_from

RULES_PATH = DATA_DIR / "rules" / "brihat-jataka-miscellaneous.yaml"
SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
BENEFICS = ("mercury", "jupiter", "venus")
STRONG = ("own", "moolatrikona", "exaltation")
KENDRA = (1, 4, 7, 10)
CLASSES = ("prishtodaya", "sirodaya", "both")


@dataclass(frozen=True)
class MiscRules:
    level: str
    checked_by: str | None
    edition: str
    pages: str
    frame: str
    raw: dict

    @property
    def servable(self) -> bool:
        return self.level in SERVABLE_LEVELS


@dataclass(frozen=True)
class Found:
    verse: str
    detail: str  # what the chart shows
    text: str  # quoted
    note: str = ""


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> MiscRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    v = raw["verification"]
    if v.get("level") in SERVABLE_LEVELS and not v.get("checked_by"):
        raise ValueError(f"{path.name}: a checked rules file needs checked_by")
    dt = raw["dasha_timing"]
    covered = [s for c in CLASSES for s in dt[c]["signs"]]
    if sorted(covered) != sorted(SIGNS):
        raise ValueError(
            f"{path.name}: dasha_timing must put each of the twelve signs in exactly one class"
        )
    for key in ("mutual", "special", "from_lagna", "kendra_pair", "tenth", "effects"):
        if not raw["karakas"][key].get("text"):
            raise ValueError(f"{path.name}: karakas.{key} needs a text")
    return MiscRules(
        v.get("level", "unchecked"),
        v.get("checked_by"),
        raw["edition"],
        str(raw.get("pages", "")),
        raw["frame"],
        raw,
    )


def _names(ps) -> str:
    return ", ".join(p.title() for p in ps)


def find(rules: MiscRules, chart: Chart) -> tuple[Found, ...] | None:
    """The chapter XXII statements that hold for this chart. None until the rules are checked."""
    if not rules.servable:
        return None
    r = rules.raw
    c = Ctx(chart)
    out: list[Found] = []
    strong = [p for p in SEVEN if c.stand(p) in STRONG]
    in_kendra = [p for p in strong if c.house[p] in KENDRA]
    karaka_planets: set[str] = set()

    k = r["karakas"]
    if len(in_kendra) >= 2:
        out.append(
            Found(
                k["mutual"]["verse"],
                f"{_names(in_kendra)} are each in an own, exaltation or moolatrikona sign and in a kendra",
                k["mutual"]["text"],
            )
        )
        karaka_planets |= set(in_kendra)
        for p in in_kendra:
            for q in in_kendra:
                if p != q and house_from(c.sign[q], c.sign[p]) == 10:
                    out.append(
                        Found(
                            k["special"]["verse"],
                            f"{p.title()} is in the 10th from {q.title()}",
                            f"{p.title()} is {q.title()}'s special karaka: {k['special']['text']}",
                        )
                    )
    in_lagna = [p for p in SEVEN if c.house[p] == 1]
    for p in in_lagna:
        helpers = [q for q in SEVEN if q != p and c.house[q] in (4, 10)]
        if helpers:
            out.append(
                Found(
                    k["from_lagna"]["verse"],
                    f"{p.title()} is in the rising sign; {_names(helpers)} in the 4th or 10th",
                    k["from_lagna"]["text"],
                )
            )
            karaka_planets |= set(helpers) | {p}
    pairs = [
        (p, q)
        for i, p in enumerate(strong)
        for q in strong[i + 1 :]
        if house_from(c.sign[p], c.sign[q]) in KENDRA
        and not (p in in_kendra and q in in_kendra)
    ]
    if pairs:
        out.append(
            Found(
                k["kendra_pair"]["verse"],
                "; ".join(f"{p.title()} and {q.title()}" for p, q in pairs)
                + " are in dignity and in kendras from one another",
                k["kendra_pair"]["text"],
            )
        )
        karaka_planets |= {x for pq in pairs for x in pq}
    for p in SEVEN:
        if c.stand(p) in ("moolatrikona", "exaltation") and c.house[p] not in KENDRA:
            for q in SEVEN:
                if (
                    q != p
                    and house_from(c.sign[p], c.sign[q]) == 10
                    and c.stand(q) in STRONG
                ):
                    friends = [
                        x
                        for x in SEVEN
                        if x not in (p, q) and c.relation(q, x) == "adhimitra"
                    ]
                    out.append(
                        Found(
                            k["tenth"]["verse"],
                            f"{p.title()} is in its {c.stand(p)} sign outside a kendra, and {q.title()} is in the 10th from it in {c.stand(q)}"
                            + (
                                f"; {q.title()}'s atimitra: {_names(friends)}"
                                if friends
                                else ""
                            ),
                            k["tenth"]["text"],
                            k["tenth"]["note"],
                        )
                    )
                    karaka_planets |= {p, q, *friends}
    if karaka_planets:
        out.append(
            Found(
                k["effects"]["verse"],
                f"karaka planets in the chart: {_names(sorted(karaka_planets, key=SEVEN.index))}",
                k["effects"]["text"],
            )
        )

    h = r["happy"]
    if c.vargottama("moon"):
        out.append(Found(h["verse"], "the Moon is vargottama", h["moon_vargottama"]))
    if c.lagna_nav == c.lagna:
        out.append(
            Found(h["verse"], "the rising navamsa is vargottama", h["lagna_vargottama"])
        )
    second = (c.sign["sun"] + 1) % 12
    on_second = [p for p in BENEFICS if c.sign[p] == second]
    if on_second:
        out.append(
            Found(
                h["verse"],
                f"{_names(on_second)} in the 2nd house from the Sun",
                h["benefics_second_from_sun"],
            )
        )
    occupied = sorted({c.house[p] for p in SEVEN if c.house[p] in KENDRA})
    if occupied:
        benefic = all(p in BENEFICS for p in SEVEN if c.house[p] in KENDRA)
        out.append(
            Found(
                h["verse"],
                f"{len(occupied)} kendra house{'s' if len(occupied) > 1 else ''} occupied"
                + (", by benefics only" if benefic else ""),
                h["kendras"],
                h["kendras_note"],
            )
        )
    if karaka_planets:
        out.append(Found(h["verse"], "karaka planets are present", h["karakas"]))

    m = r["manhood"]
    lord_moon, lord_lagna = SIGN_LORDS[c.sign["moon"]], SIGN_LORDS[c.lagna]
    placed = [
        f"{n} ({p.title()})"
        for n, p in (
            ("Jupiter", "jupiter"),
            ("the lord of the Moon's sign", lord_moon),
            ("the lord of the ascendant", lord_lagna),
        )
        if c.house[p] in KENDRA
    ]
    if placed:
        out.append(
            Found(
                m["verse"],
                f"in a kendra: {', '.join(dict.fromkeys(placed))}",
                m["text"],
            )
        )

    d = r["dasha_timing"]
    for p in SEVEN:
        s = SIGNS[c.sign[p]]
        cls = next(x for x in CLASSES if s in d[x]["signs"])
        out.append(
            Found(
                d["verse"],
                f"{p.title()} is in {s}",
                f"{d['lead']} {d[cls]['text']}",
                d["note"],
            )
        )
    return tuple(out)
