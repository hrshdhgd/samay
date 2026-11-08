"""Build the bundled place database from GeoNames dumps (https://download.geonames.org/export/dump/).

A pure function of the input files: the same files always give the same database bytes, which is
what lets data/gazetteer.lock pin the result by hash.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from .names import fold, skeleton

# Alternate-name languages kept: Hindi, Marathi, Ukrainian, Russian, Italian, English, and names
# without a language tag. Links, postcodes, airport codes and other languages are dropped.
LANGUAGES = frozenset({"hi", "mr", "uk", "ru", "it", "en", ""})
FEATURE_CLASSES = frozenset("PA")
BATCH = 50_000

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE countries (iso TEXT PRIMARY KEY, iso3 TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE places (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL,
    admin1 TEXT, admin2 TEXT, admin1_name TEXT, admin2_name TEXT,
    latitude REAL NOT NULL, longitude REAL NOT NULL, tz TEXT NOT NULL,
    population INTEGER NOT NULL, fclass TEXT NOT NULL, fcode TEXT NOT NULL
);
CREATE TABLE names (
    place_id INTEGER NOT NULL, fold TEXT NOT NULL, skel TEXT NOT NULL,
    PRIMARY KEY (place_id, fold)
) WITHOUT ROWID;
CREATE INDEX names_fold ON names (fold);
CREATE INDEX names_skel ON names (skel);
"""


def _rows(f: io.TextIOBase) -> Iterator[list[str]]:
    for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
        if row and not row[0].startswith("#"):
            yield row


def _read(src: Path, stem: str) -> Iterator[list[str]]:
    zipped, plain = src / f"{stem}.zip", src / f"{stem}.txt"
    if zipped.exists():
        with zipfile.ZipFile(zipped) as z, z.open(f"{stem}.txt") as raw:
            yield from _rows(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
    elif plain.exists():
        with plain.open(encoding="utf-8", newline="") as f:
            yield from _rows(f)
    else:
        raise FileNotFoundError(f"missing GeoNames file {stem}.zip or {stem}.txt in {src}")


def _name_row(place_id: int, text: str) -> tuple[int, str, str] | None:
    key = fold(text)
    return (place_id, key, skeleton(text)) if key else None


def build(
    src: Path,
    out: Path,
    countries: Iterable[str],
    snapshot: str,
    sources: dict[str, str] | None = None,
) -> None:
    """Write `out` from the dumps in `src`: cities500 plus a full file per country in `countries`."""
    countries = [c.upper() for c in countries]
    tmp = out.with_name(out.name + ".part")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)

    conn.executemany(
        "INSERT INTO countries VALUES (?, ?, ?)",
        sorted((r[0], r[1], r[4]) for r in _read(src, "countryInfo") if len(r) > 4),
    )
    admin1 = {r[0]: r[1] for r in _read(src, "admin1CodesASCII") if len(r) > 1}
    admin2 = {r[0]: r[1] for r in _read(src, "admin2Codes") if len(r) > 1}

    ids: set[int] = set()
    places: list[tuple] = []
    names: list[tuple] = []

    def flush() -> None:
        conn.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", places)
        conn.executemany("INSERT OR IGNORE INTO names VALUES (?,?,?)", names)
        places.clear()
        names.clear()

    for stem in ("cities500", *countries):
        for r in _read(src, stem):
            if len(r) < 18:
                continue
            gid = int(r[0])
            if gid in ids or r[6] not in FEATURE_CLASSES or r[7].startswith("PCL") or not r[17]:
                continue
            ids.add(gid)
            cc, a1, a2 = r[8], r[10], r[11]
            places.append((
                gid, r[1], cc, a1 or None, a2 or None,
                admin1.get(f"{cc}.{a1}"), admin2.get(f"{cc}.{a1}.{a2}"),
                float(r[4]), float(r[5]), r[17], int(r[14] or 0), r[6], r[7],
            ))
            names.extend(n for n in (_name_row(gid, r[1]), _name_row(gid, r[2])) if n)
            if len(places) >= BATCH:
                flush()
    flush()

    for r in _read(src, "alternateNamesV2"):
        if len(r) < 4 or r[2] not in LANGUAGES:
            continue
        gid = int(r[1])
        if gid in ids and (n := _name_row(gid, r[3])):
            names.append(n)
            if len(names) >= BATCH:
                flush()
    flush()

    meta = {
        "schema": "1",
        "snapshot": snapshot,
        "countries": ",".join(countries),
        "sources": json.dumps(sources or {}, sort_keys=True),
    }
    conn.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
    conn.commit()
    conn.close()
    tmp.replace(out)
