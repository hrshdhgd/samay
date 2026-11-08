"""Report models shared by every front end. All frozen; renderers only read them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .engine.ephemeris import Chart
from .engine.geo import Place
from .engine.profiles import DEFAULT_PROFILE
from .engine.rules import Rule
from .engine.vedic import Period


@dataclass(frozen=True)
class BirthInput:
    """Exactly what the user typed and chose."""

    date_text: str
    time_text: str
    place_text: str
    place_choice: str | None = None
    fold: int | None = None
    profile: str = DEFAULT_PROFILE
    approx_for: str | None = None  # birthplace the user named, when a nearby town stands in for it


@dataclass(frozen=True)
class Provenance:
    offset: timedelta
    offset_source: str
    confidence: str
    warning: str | None = None
    place_approximate: bool = False
    approx_note: str | None = None


@dataclass(frozen=True)
class ResolvedBirth:
    local: datetime
    utc: datetime
    place: Place
    provenance: Provenance
    profile: str = DEFAULT_PROFILE


@dataclass(frozen=True)
class NeedsDisambiguation:
    kind: Literal["place", "time"]
    options: tuple[Place, ...] | tuple[datetime, ...]


@dataclass(frozen=True)
class VersionStamp:
    git_sha: str
    rules_hash: str
    profile_id: str
    profile_hash: str
    timestd_version: str
    tzdata_version: str
    ephemeris: str
    gazetteer: str

    def short(self) -> str:
        return (
            f"samay {self.git_sha} · rules {self.rules_hash} · profile {self.profile_id}@{self.profile_hash}"
            f" · timestd {self.timestd_version} · tzdata {self.tzdata_version}"
            f" · {self.ephemeris} · {self.gazetteer}"
        )


@dataclass(frozen=True)
class NatalReport:
    birth: ResolvedBirth
    chart: Chart
    dashas: tuple[Period, ...]
    yogas: tuple[Rule, ...]
    stamp: VersionStamp
    validated: bool


@dataclass(frozen=True)
class TodayReport:
    natal: NatalReport
    sky: Chart
    now: datetime
    current_dasha: tuple[Period, Period] | None
    transit_houses: tuple[tuple[str, int], ...]
