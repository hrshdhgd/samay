"""Tradition profiles: one YAML file per lineage, holding every disputed calculation choice."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .ephemeris import AYANAMSAS, NODES
from .errors import UnknownProfile
from .paths import PROFILES_DIR

DEFAULT_PROFILE = "parashari-lahiri"
SUPPORTED_HOUSES = {"whole_sign"}
SUPPORTED_METHODS = {"drik"}


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    ayanamsa: str
    node: str
    houses: str
    dasha_year_days: float
    method: str
    schools: tuple[str, ...]
    conflict_rule: str
    validated: bool
    citations: tuple[dict, ...]
    sha256: str


def _check(field_name: str, value: object, allowed: set) -> None:
    if value not in allowed:
        raise ValueError(f"profile field {field_name!r}: unsupported value {value!r}")


@lru_cache(maxsize=16)
def load_profile(profile_id: str = DEFAULT_PROFILE, directory: Path = PROFILES_DIR) -> Profile:
    path = directory / f"{profile_id}.yaml"
    if not path.is_file():
        raise UnknownProfile(f"unknown tradition profile {profile_id!r}")
    raw_bytes = path.read_bytes()
    raw = yaml.safe_load(raw_bytes)
    if raw.get("id") != profile_id:
        raise ValueError(f"{path.name}: id {raw.get('id')!r} does not match file name")
    _check("ayanamsa", raw["ayanamsa"], set(AYANAMSAS))
    _check("node", raw["node"], set(NODES))
    _check("houses", raw["houses"], SUPPORTED_HOUSES)
    _check("method", raw["method"], SUPPORTED_METHODS)
    if float(raw["dasha_year_days"]) <= 0:
        raise ValueError("profile field 'dasha_year_days' must be positive")
    return Profile(
        id=raw["id"],
        name=raw["name"],
        ayanamsa=raw["ayanamsa"],
        node=raw["node"],
        houses=raw["houses"],
        dasha_year_days=float(raw["dasha_year_days"]),
        method=raw["method"],
        schools=tuple(raw["schools"]),
        conflict_rule=raw["conflict_rule"],
        validated=bool(raw["validated"]),
        citations=tuple(raw.get("citations") or ()),
        sha256=hashlib.sha256(raw_bytes).hexdigest()[:12],
    )
