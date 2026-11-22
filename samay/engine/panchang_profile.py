"""The family's panchang conventions: one YAML file, validated on load."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .daylight import HORIZON_DEGREES
from .ephemeris import AYANAMSAS
from .errors import UnknownProfile
from .observances import ANCHORS, KSHAYA_CHOICES, VRIDDHI_CHOICES, Rule, Viddha
from .paths import PROFILES_DIR

DEFAULT_PANCHANG_PROFILE = "panchang-family"
SAMPRADAYAS = (None, "smarta", "madhva", "vaishnava")


@dataclass(frozen=True)
class ObservanceSpec:
    name: str
    label: str
    rules: dict[str, Rule]  # tradition name -> rule, or just "all"
    verified: bool  # False: the bot makes no day claim from these rules
    source: dict


@dataclass(frozen=True)
class PanchangProfile:
    id: str
    sampradaya: str | None
    ayanamsa: str
    sunrise_definition: str
    margin_minutes: int
    observances: dict[str, ObservanceSpec]
    sha256: str


def _check(field: str, value: object, allowed) -> None:
    if value not in allowed:
        raise ValueError(f"profile field {field!r}: unsupported value {value!r}")


def _rule(where: str, raw: dict) -> Rule:
    tithis = tuple(int(t) for t in raw["tithis"])
    if not tithis or not all(1 <= t <= 30 for t in tithis):
        raise ValueError(f"{where}: tithis must be numbers 1-30")
    _check(f"{where} anchor", raw["anchor"], ANCHORS)
    _check(f"{where} on_kshaya", raw.get("on_kshaya", "start_day"), KSHAYA_CHOICES)
    _check(f"{where} on_vriddhi", raw.get("on_vriddhi", "first"), VRIDDHI_CHOICES)
    start, end = int(raw["start_minutes"]), int(raw["end_minutes"])
    if start > end:
        raise ValueError(f"{where}: start_minutes is after end_minutes")
    v = raw.get("viddha")
    viddha = None if v is None else Viddha(tuple(int(t) for t in v["tithis"]), v["anchor"], int(v["start_minutes"]), int(v["end_minutes"]))
    if viddha is not None:
        _check(f"{where} viddha anchor", viddha.anchor, ANCHORS)
    return Rule(tithis, raw["anchor"], start, end, raw.get("on_kshaya", "start_day"), raw.get("on_vriddhi", "first"), viddha)


@lru_cache(maxsize=4)
def load_panchang_profile(profile_id: str = DEFAULT_PANCHANG_PROFILE, directory: Path = PROFILES_DIR) -> PanchangProfile:
    path = directory / f"{profile_id}.yaml"
    if not path.is_file():
        raise UnknownProfile(f"unknown panchang profile {profile_id!r}")
    raw_bytes = path.read_bytes()
    raw = yaml.safe_load(raw_bytes)
    _check("sampradaya", raw.get("sampradaya"), SAMPRADAYAS)
    _check("ayanamsa", raw["ayanamsa"], set(AYANAMSAS))
    _check("sunrise_definition", raw["sunrise_definition"], set(HORIZON_DEGREES))
    margin = int(raw["ambiguity_margin_minutes"])
    if margin < 0:
        raise ValueError("profile field 'ambiguity_margin_minutes' must not be negative")
    observances = {}
    for name, spec in raw["observances"].items():
        rules = {who: _rule(f"{name}.{who}", r) for who, r in spec["rules"].items()}
        sampradaya = raw.get("sampradaya")
        if sampradaya is not None and "all" not in rules and sampradaya not in rules:
            raise ValueError(f"profile field 'sampradaya': observance {name!r} has no rule for tradition {sampradaya!r}")
        observances[name] = ObservanceSpec(name, spec["label"], rules, bool(spec["verified"]), spec["source"])
    return PanchangProfile(raw["id"], raw.get("sampradaya"), raw["ayanamsa"], raw["sunrise_definition"], margin,
                           observances, hashlib.sha256(raw_bytes).hexdigest()[:12])
