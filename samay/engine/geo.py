"""Offline place lookup.

Backend: GeoNames cities >= 15k population via geonamescache. Plan 1B replaces the backend with
a bundled worldwide gazetteer; `find_places` keeps its signature.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    country: str
    admin1: str | None
    admin2: str | None
    latitude: float
    longitude: float
    tz: str
    population: int

    @property
    def label(self) -> str:
        region = f", {self.admin1}" if self.admin1 else ""
        return f"{self.name}{region}, {self.country}"


@lru_cache(maxsize=1)
def _index() -> dict[str, list[Place]]:
    """Casefolded name and alternate names -> places. Built once."""
    import geonamescache

    index: dict[str, list[Place]] = defaultdict(list)
    for c in geonamescache.GeonamesCache().get_cities().values():
        place = Place(
            id=str(c["geonameid"]),
            name=c["name"],
            country=c["countrycode"],
            admin1=c.get("admin1code") or None,
            admin2=None,
            latitude=c["latitude"],
            longitude=c["longitude"],
            tz=c["timezone"],
            population=c["population"],
        )
        keys = {c["name"].casefold(), *(a.casefold() for a in c.get("alternatenames", []) if a)}
        for key in keys:
            index[key].append(place)
    return dict(index)


def find_places(query: str, limit: int = 3) -> list[Place]:
    """'Pune' or 'Pune, IN'. Most populous first; [] when nothing matches."""
    name, _, cc = (s.strip() for s in query.partition(","))
    matches = _index().get(name.casefold(), [])
    if cc:
        matches = [p for p in matches if p.country == cc.upper()]
    return sorted(matches, key=lambda p: -p.population)[:limit]


@lru_cache(maxsize=1)
def _by_id() -> dict[str, Place]:
    return {p.id: p for places in _index().values() for p in places}


def get_place(place_id: str) -> Place | None:
    return _by_id().get(place_id)
