#!/usr/bin/env python3
"""Download GeoNames dumps once, build data/gazetteer.sqlite and pin it in data/gazetteer.lock.

    uv run python scripts/build_gazetteer.py            # build (downloads on first run)
    uv run python scripts/build_gazetteer.py --verify   # check the database against the lock

The Dockerfile only copies the finished database and runs --verify; nothing is downloaded or
built on the server. To refresh, delete data/geonames-src/ and rebuild: the snapshot date and
every hash change, which is the deliberate part.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from samay.engine.gazetteer_build import build

BASE = "https://download.geonames.org/export/dump/"
SHARED = ["cities500.zip", "countryInfo.txt", "admin1CodesASCII.txt", "admin2Codes.txt", "alternateNamesV2.zip"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, dest_dir: Path) -> Path:
    dest = dest_dir / name
    if dest.exists():
        return dest
    print(f"downloading {name} ...", flush=True)
    part = dest.with_name(name + ".part")
    with urllib.request.urlopen(BASE + name, timeout=120) as r, part.open("wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    part.replace(dest)
    return dest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--countries", default=os.environ.get("GEONAMES_FULL_COUNTRIES", "IN,US,UA,IT"))
    p.add_argument("--src", type=Path, default=ROOT / "data" / "geonames-src")
    p.add_argument("--out", type=Path, default=ROOT / "data" / "gazetteer.sqlite")
    p.add_argument("--lock", type=Path, default=ROOT / "data" / "gazetteer.lock")
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()

    if args.verify:
        lock = json.loads(args.lock.read_text())
        actual = sha256(args.out)
        ok = actual == lock["database_sha256"]
        print(("ok" if ok else f"MISMATCH: {actual} != {lock['database_sha256']}"), args.out)
        return 0 if ok else 1

    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    args.src.mkdir(parents=True, exist_ok=True)
    files = SHARED + [f"{c}.zip" for c in countries]
    hashes = {name: sha256(fetch(name, args.src)) for name in files}

    snapshot = datetime.now(UTC).strftime("%Y-%m-%d")
    if args.lock.exists():
        old = json.loads(args.lock.read_text())
        if old.get("sources") == hashes and old.get("countries") == countries:
            snapshot = old["snapshot"]  # same inputs: keep the original snapshot date

    print("building database ...", flush=True)
    build(args.src, args.out, countries, snapshot, hashes)
    lock = {"snapshot": snapshot, "countries": countries, "sources": hashes, "database_sha256": sha256(args.out)}
    args.lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.0f} MB), snapshot {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
