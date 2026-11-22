"""Report models shared by every front end. All frozen; renderers only read them."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from .engine.ephemeris import Chart
from .engine.geo import Place
from .engine.gochara import Stay
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

    def code(self) -> str:
        """Eight-character reference for this exact combination of data and rule versions."""
        return hashlib.sha256(self.short().encode()).hexdigest()[:8]

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


@dataclass(frozen=True)
class OutlookReport:
    """A period ahead (a week to several years): where the planets go, counted from the natal Moon sign, with the
    text's transit results (Phaladeepika ch. 26), and the dasha sub-chapters that begin inside the period.
    """

    natal: NatalReport
    span: str  # week, fortnight, month, year or years
    start: datetime  # UTC
    end: datetime  # UTC
    tz: str  # the timezone dates are shown in
    moon_sign: int
    stays: tuple[Stay, ...]
    dasha_at_start: tuple[Period, Period] | None
    dasha_changes: tuple[
        tuple[str, Period], ...
    ]  # (mahadasha lord, antardasha) for each sub-chapter that begins
    rules_level: str
    rules_edition: str
    rules_pages: str
    antardasha: tuple[
        tuple[str, str, str, int], ...
    ] = ()  # (mahadasha, antardasha, result, verse): Phaladeepika 21
    antardasha_edition: str = ""
    antardasha_pages: str = ""
    antardasha_checked: bool = False
    ashtaka_checked: bool = (
        False  # the points on each stay are shown only once the ashtakavarga tables are checked
    )
    ashtaka_meaning: tuple[tuple[int, str], ...] = ()  # (points, what the text says), Phaladeepika 23.11
    ashtaka_variants: int = 0  # lists where Phaladeepika's printed table differs from the tables used


@dataclass(frozen=True)
class ObservanceDay:
    """An observance the rules name for a day: its label, primary day, alternates, and its checked explanation."""

    name: str
    label: str
    primary: date | None
    kind: str  # single | kshaya | vriddhi
    alternates: tuple[
        tuple[date, str], ...
    ]  # (day, reason); each day once, several reasons joined with " and "
    explanation: str | None  # a checked entry's own words, or None


@dataclass(frozen=True)
class PanchangReport:
    place_label: str
    tz: str
    facts: object  # panchang.DayFacts
    tulu: object  # tulu.TuluDate
    cutoff: str  # the Tulu day-1 rule used
    observances: tuple[ObservanceDay, ...]  # only observances whose rules are verified and touch the day
    needs_sampradaya: bool  # True when day claims were withheld because the family's tradition is not set
    claims_withheld: bool  # True when some observance rules are not verified yet


@dataclass(frozen=True)
class NextObservanceReport:
    place_label: str
    tz: str
    name: str
    label: str
    found: ObservanceDay | None
    claim_available: bool  # False when the rule is unverified or the tradition is not set
    needs_sampradaya: bool


@dataclass(frozen=True)
class ObservanceListReport:
    """Every day verified rules name in a range of local days, for a list ("Ekadashi dates in 2027")."""

    place_label: str
    tz: str
    first: date
    last: date
    labels: tuple[str, ...]  # the observances asked about, in profile order
    filtered: bool  # True when the question named observances, False for all of them
    days: tuple[ObservanceDay, ...]  # by primary day (or first alternate); explanation always None
    withheld: tuple[str, ...]  # labels of asked-about observances whose rules are not verified
    needs_sampradaya: bool  # True when some days were withheld because the family's tradition is not set
    too_long: bool  # True when the range is longer than LIST_MAX_DAYS; nothing was worked out
