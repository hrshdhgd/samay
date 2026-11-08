"""Local clock time -> UTC, with curated historical time standards overriding tzdata.

Curated entries live in data/time_standards/*.yaml and are added only from cited primary
sources (sub-project 2). Without a matching entry, tzdata decides and the confidence reflects
how far tzdata can be trusted for that era.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .errors import NonexistentTime
from .geo import Place
from .paths import TIME_STANDARDS_DIR

CONFIDENCES = ("verified", "probable", "tzdata", "low")
_REQUIRED = {"country", "from", "to", "offset", "name", "confidence", "source"}
TZDATA_RELIABLE_FROM = 1970
# tzdata models all of India as one zone; local standards (e.g. Bombay Time) are missing.
INDIA_UNIFIED_FROM = date(1956, 1, 1)
INDIA_WARNING = (
    "Before 1956 some Indian cities kept their own local time (for example Bombay Time). "
    "This birth time has not been checked against those records."
)


@dataclass(frozen=True)
class StandardEntry:
    country: str
    admin1: str | None
    admin2: str | None
    start: date
    end: date
    offset: timedelta
    name: str
    confidence: str
    source: dict


@dataclass(frozen=True)
class TimeResolution:
    utc: datetime
    offset: timedelta
    source: str
    confidence: str
    warning: str | None = None


@dataclass(frozen=True)
class AmbiguousTime:
    """The local clock showed this time twice; options are both UTC instants, earliest first."""

    options: tuple[datetime, datetime]


def _parse_offset(text: str) -> timedelta:
    sign = -1 if text.startswith("-") else 1
    parts = [int(p) for p in text.lstrip("+-").split(":")]
    h, m, s = (parts + [0, 0])[:3]
    return sign * timedelta(hours=h, minutes=m, seconds=s)


@lru_cache(maxsize=4)
def load_standards(directory: Path = TIME_STANDARDS_DIR) -> tuple[StandardEntry, ...]:
    entries = []
    for path in sorted(directory.glob("*.yaml")):
        for i, raw in enumerate(yaml.safe_load(path.read_text(encoding="utf-8")) or []):
            missing = _REQUIRED - raw.keys()
            if missing:
                raise ValueError(f"{path.name}[{i}]: missing {sorted(missing)}")
            if raw["confidence"] not in CONFIDENCES:
                raise ValueError(f"{path.name}[{i}]: bad confidence {raw['confidence']!r}")
            if not {"text", "locus", "verified"} <= raw["source"].keys():
                raise ValueError(f"{path.name}[{i}]: source needs text, locus and verified")
            entries.append(StandardEntry(
                country=raw["country"],
                admin1=raw.get("admin1"),
                admin2=raw.get("admin2"),
                start=raw["from"],
                end=raw["to"],
                offset=_parse_offset(str(raw["offset"])),
                name=raw["name"],
                confidence=raw["confidence"],
                source=raw["source"],
            ))
    return tuple(entries)


def _match(local: datetime, place: Place, entries: tuple[StandardEntry, ...]) -> StandardEntry | None:
    best, best_score = None, -1
    for e in entries:
        if e.country != place.country or not e.start <= local.date() < e.end:
            continue
        if e.admin1 and e.admin1 != place.admin1:
            continue
        if e.admin2 and e.admin2 != place.admin2:
            continue
        score = bool(e.admin1) + bool(e.admin2)
        if score > best_score:
            best, best_score = e, score
    return best


def _fmt_offset(offset: timedelta) -> str:
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    h, rem = divmod(abs(total), 3600)
    m, s = divmod(rem, 60)
    return f"UTC{sign}{h:02d}:{m:02d}" + (f":{s:02d}" if s else "")


def resolve_local_time(
    local: datetime,
    place: Place,
    fold: int | None = None,
    entries: tuple[StandardEntry, ...] | None = None,
) -> TimeResolution | AmbiguousTime:
    if local.tzinfo is not None:
        raise ValueError("local must be a naive wall-clock time")
    entries = load_standards() if entries is None else entries

    entry = _match(local, place, entries)
    if entry:
        cite = entry.source["text"] + (f", {entry.source['locus']}" if entry.source.get("locus") else "")
        return TimeResolution(
            utc=(local - entry.offset).replace(tzinfo=timezone.utc),
            offset=entry.offset,
            source=f"{_fmt_offset(entry.offset)} {entry.name} ({cite})",
            confidence=entry.confidence,
        )

    zone = ZoneInfo(place.tz)
    first, second = local.replace(tzinfo=zone, fold=0), local.replace(tzinfo=zone, fold=1)
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != local:
        raise NonexistentTime(f"{local:%Y-%m-%d %H:%M} never occurred on clocks in {place.tz}")
    u0, u1 = first.astimezone(timezone.utc), second.astimezone(timezone.utc)
    if u0 != u1 and fold is None:
        return AmbiguousTime(options=tuple(sorted((u0, u1))))
    chosen = second if fold == 1 else first
    offset = chosen.utcoffset()

    confidence = "tzdata" if local.year >= TZDATA_RELIABLE_FROM else "low"
    warning = INDIA_WARNING if place.country == "IN" and local.date() < INDIA_UNIFIED_FROM else None
    return TimeResolution(
        utc=chosen.astimezone(timezone.utc),
        offset=offset,
        source=f"{_fmt_offset(offset)} {chosen.tzname()} (tzdata {place.tz})",
        confidence=confidence,
        warning=warning,
    )
