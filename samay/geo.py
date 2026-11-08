"""Offline place lookup (GeoNames cities >= 15k population, bundled in geonamescache)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Place:
    name: str
    country: str
    latitude: float
    longitude: float
    tz: str


@lru_cache(maxsize=1)
def _cities() -> list[dict]:
    import geonamescache

    return list(geonamescache.GeonamesCache().get_cities().values())


def find_place(query: str) -> Place | None:
    """'Pune' or 'Pune, IN'. Picks the most populous match; caller should echo it back."""
    name, _, cc = (s.strip() for s in query.partition(","))
    key, cc = name.casefold(), cc.upper()
    matches = [
        c for c in _cities()
        if (c["name"].casefold() == key or key in (a.casefold() for a in c.get("alternatenames", [])))
        and (not cc or c["countrycode"] == cc)
    ]
    if not matches:
        return None
    c = max(matches, key=lambda c: c["population"])
    return Place(c["name"], c["countrycode"], c["latitude"], c["longitude"], c["timezone"])


def local_to_utc(local: datetime, tz: str) -> datetime:
    """Interpret a naive local birth time in an IANA zone (historical offsets/DST via tzdata)."""
    # TODO: ambiguous/nonexistent times around DST changes; ask the user when fold matters.
    return local.replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)
