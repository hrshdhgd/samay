"""Offline place lookup over the bundled GeoNames gazetteer (data/gazetteer.sqlite).

Built by scripts/build_gazetteer.py; opened read-only here. Queries look like "Pune",
"Pune, IN" or "Maplewood, MN, USA": a name, then any number of qualifiers (country code or
name, state, district) that must all match.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from .errors import GazetteerMissing
from .names import fold, skeleton
from .paths import GAZETTEER_PATH

SKELETON_MIN_SCORE = 75  # phonetic-bucket candidates below this similarity are not offered
FUZZY_MIN_SCORE = 85  # prefix-bucket candidates (other scripts, or no phonetic hit)
NEAR_TOP = 10  # candidates within this many similarity points of the best are all offered
POPULATION_WEIGHT = 4  # ranking bonus per power of ten of population, in similarity points
CHUNK = 500

_db_path: Path = GAZETTEER_PATH


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
    admin1_name: str | None = None
    admin2_name: str | None = None
    country_name: str | None = None

    @property
    def label(self) -> str:
        """'Name, District, State, CC' with empty or repeated parts left out."""
        parts: list[str] = []
        for part in (self.name, self.admin2_name, self.admin1_name, self.country):
            if part and (not parts or part != parts[-1]):
                parts.append(part)
        return ", ".join(parts)


def configure(path: Path | None) -> None:
    """Point lookups at another database (tests); None restores the default."""
    global _db_path
    _db_path = path or GAZETTEER_PATH
    _conn.cache_clear()


@lru_cache(maxsize=1)
def _conn() -> sqlite3.Connection:
    if not _db_path.exists():
        raise GazetteerMissing(
            f"Place database not found at {_db_path}. Run: uv run python scripts/build_gazetteer.py"
        )
    conn = sqlite3.connect(f"file:{_db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_SELECT = (
    "SELECT p.id, p.name, p.country, p.admin1, p.admin2, p.admin1_name, p.admin2_name, p.latitude,"
    " p.longitude, p.tz, p.population, p.fclass, c.name AS country_name, c.iso3"
    " FROM places p LEFT JOIN countries c ON c.iso = p.country"
)


def _place(row: sqlite3.Row) -> Place:
    return Place(
        id=str(row["id"]), name=row["name"], country=row["country"], admin1=row["admin1"],
        admin2=row["admin2"], latitude=row["latitude"], longitude=row["longitude"], tz=row["tz"],
        population=row["population"], admin1_name=row["admin1_name"], admin2_name=row["admin2_name"],
        country_name=row["country_name"],
    )


def _rows(ids: list[int]) -> list[sqlite3.Row]:
    out: list[sqlite3.Row] = []
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i : i + CHUNK]
        marks = ",".join("?" * len(chunk))
        out.extend(_conn().execute(f"{_SELECT} WHERE p.id IN ({marks})", chunk))
    return out


def _candidates(name: str) -> dict[int, float]:
    """place id -> similarity (100 for an exact folded match)."""
    key = fold(name)
    if not key:
        return {}
    conn = _conn()
    scores: dict[int, float] = {
        r[0]: 100.0 for r in conn.execute("SELECT place_id FROM names WHERE fold = ?", (key,))
    }
    skel = skeleton(name)
    if skel:  # spelling variants, even when exact matches exist: "Kolapur" is probably Kolhapur
        for pid, other in conn.execute("SELECT place_id, fold FROM names WHERE skel = ?", (skel,)):
            score = fuzz.ratio(key, other)
            if score >= SKELETON_MIN_SCORE and score > scores.get(pid, 0):
                scores[pid] = score
    if scores:
        return scores

    prefix = key[:2]
    pool = conn.execute(
        "SELECT place_id, fold FROM names WHERE fold >= ? AND fold < ?", (prefix, prefix + "\U0010ffff")
    ).fetchall()
    best = process.extract(key, [f for _, f in pool], scorer=fuzz.ratio, score_cutoff=FUZZY_MIN_SCORE, limit=200)
    for _, score, idx in best:
        pid = pool[idx][0]
        if score > scores.get(pid, 0):
            scores[pid] = score
    return scores


def find_places(query: str, limit: int = 3) -> list[Place]:
    """Best matches for 'Name[, qualifier...]', exact names and close spelling variants.

    Administrative areas (districts, provinces) are offered only when no populated place matches.
    Candidates within NEAR_TOP points of the best similarity are ranked by similarity plus a small
    population prior; places that would show the same label are collapsed into the best one.
    """
    name, *qualifiers = (part.strip() for part in query.split(","))
    wanted = [q for q in (fold(q) for q in qualifiers) if q]
    scores = _candidates(name)
    if not scores:
        return []

    matched: list[tuple[float, sqlite3.Row]] = []
    for row in _rows(list(scores)):
        keys = {fold(v) for v in (row["country"], row["country_name"], row["iso3"], row["admin1"],
                                   row["admin1_name"], row["admin2_name"]) if v}
        if all(q in keys for q in wanted):
            matched.append((scores[row["id"]], row))
    if any(row["fclass"] == "P" for _, row in matched):
        matched = [m for m in matched if m[1]["fclass"] == "P"]
    if not matched:
        return []

    cutoff = max(score for score, _ in matched) - NEAR_TOP
    ranked = sorted(
        (m for m in matched if m[0] >= cutoff),
        key=lambda m: (-(m[0] + POPULATION_WEIGHT * math.log10(m[1]["population"] + 1)), m[1]["id"]),
    )
    out: list[Place] = []
    for _, row in ranked:
        place = _place(row)
        if all(place.label != seen.label for seen in out):
            out.append(place)
    return out[:limit]


def get_place(place_id: str) -> Place | None:
    rows = _conn().execute(f"{_SELECT} WHERE p.id = ?", (int(place_id),)).fetchall()
    return _place(rows[0]) if rows else None


def gazetteer_stamp() -> str:
    """'geonames <snapshot> <db hash>' for version stamps."""
    snapshot = _conn().execute("SELECT value FROM meta WHERE key = 'snapshot'").fetchone()[0]
    lock = _db_path.with_name("gazetteer.lock")
    digest = json.loads(lock.read_text())["database_sha256"][:12] if lock.exists() else "unlocked"
    return f"geonames {snapshot} {digest}"
