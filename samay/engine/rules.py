"""Declarative rule engine. Rules live in rules/*.yaml with source provenance.

Condition DSL (all keys optional, combinable):
  house_from: {planet, reference: <planet|lagna>, houses: [1, 4, 7, 10]}
  same_sign: [planet, planet, ...]
  in_sign:   {planet, signs: [Aries, ...]}          # English sign names
  in_house:  {planet, houses: [...]}                 # from lagna
  all: [cond, ...]   any: [cond, ...]   not: cond
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .ephemeris import Chart
from .paths import RULES_DIR
from .vedic import SIGNS, sign_index


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    school: str
    source: dict
    when: dict
    effect: str
    tags: list = field(default_factory=list)


@dataclass(frozen=True)
class Context:
    signs: dict[str, int]  # body -> sign index, includes "lagna"

    @classmethod
    def from_chart(cls, chart: Chart) -> Context:
        signs = {p: sign_index(pl.longitude) for p, pl in chart.planets.items()}
        signs["lagna"] = sign_index(chart.ascendant)
        return cls(signs)


def _house(ctx: Context, planet: str, reference: str) -> int:
    return (ctx.signs[planet] - ctx.signs[reference]) % 12 + 1


def evaluate(cond: dict[str, Any], ctx: Context) -> bool:
    for key, arg in cond.items():
        if key == "all":
            ok = all(evaluate(c, ctx) for c in arg)
        elif key == "any":
            ok = any(evaluate(c, ctx) for c in arg)
        elif key == "not":
            ok = not evaluate(arg, ctx)
        elif key == "house_from":
            ok = _house(ctx, arg["planet"], arg.get("reference", "lagna")) in arg["houses"]
        elif key == "in_house":
            ok = _house(ctx, arg["planet"], "lagna") in arg["houses"]
        elif key == "same_sign":
            ok = len({ctx.signs[p] for p in arg}) == 1
        elif key == "in_sign":
            ok = SIGNS[ctx.signs[arg["planet"]]] in arg["signs"]
        else:
            raise ValueError(f"unknown condition: {key}")
        if not ok:
            return False
    return True


def load_rules(directory: Path = RULES_DIR, schools: Iterable[str] | None = None) -> list[Rule]:
    """All rules in `directory`, optionally limited to the given schools."""
    rules = []
    for path in sorted(directory.glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            rules.append(Rule(**raw))
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule ids")
    if schools is not None:
        wanted = set(schools)
        rules = [r for r in rules if r.school in wanted]
    return rules


def rules_hash(directory: Path = RULES_DIR) -> str:
    """Short content hash of every rule file, for version stamps."""
    h = hashlib.sha256()
    for path in sorted(directory.glob("*.yaml")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


def fired(chart: Chart, rules: list[Rule] | None = None) -> list[Rule]:
    ctx = Context.from_chart(chart)
    return [r for r in (rules if rules is not None else load_rules()) if evaluate(r.when, ctx)]
