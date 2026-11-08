#!/usr/bin/env python3
"""Cut a small GeoNames extract for tests (tests/fixtures/geonames-mini) from the cached dumps.

    uv run python scripts/make_gazetteer_fixture.py [--village GEONAMEID ...]

Run scripts/build_gazetteer.py first so data/geonames-src/ is populated. The extract keeps the
same file layout as the real dumps, so tests exercise the real builder.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from samay.engine.gazetteer_build import LANGUAGES, _read

COUNTRIES = ["IN", "US", "UA", "IT"]
# (name, country, how many of the most populous, optional admin1 that must be included)
PICKS = [
    ("Pune", "IN", 1, None),
    ("Mumbai", "IN", 1, None),
    ("Aurangabad", "IN", 3, None),
    ("Kolhapur", "IN", 1, None),
    ("Nagpur", "IN", 1, None),
    ("Kolkata", "IN", 1, None),
    ("Kyiv", "UA", 1, None),
    ("Kharkiv", "UA", 1, None),
    ("Springfield", "US", 4, None),
    ("Maplewood", "US", 2, "MN"),
    ("New York City", "US", 1, None),
    ("Chicago", "US", 1, None),
    ("London", "GB", 1, None),
    ("London", "CA", 1, None),
    ("Forlì", "IT", 1, None),
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, default=ROOT / "data" / "geonames-src")
    p.add_argument("--out", type=Path, default=ROOT / "tests" / "fixtures" / "geonames-mini")
    p.add_argument("--village", type=int, action="append", default=[], help="extra geonameid from a country file (any class)")
    args = p.parse_args()

    by_stem: dict[str, list[list[str]]] = {}
    for stem in ("cities500", *COUNTRIES):
        by_stem[stem] = [r for r in _read(args.src, stem) if len(r) >= 18 and r[6] in ("P", "A")]

    chosen: dict[int, tuple[str, list[str]]] = {}
    for name, cc, n, must in PICKS:
        hits: list[tuple[str, list[str]]] = []
        for stem in ("cities500", *COUNTRIES):
            hits += [(stem, r) for r in by_stem[stem] if r[6] == "P" and r[8] == cc and name in (r[1], r[2])]
        hits.sort(key=lambda h: -int(h[1][14] or 0))
        seen: set[str] = set()
        unique = []
        for h in hits:  # US places appear in both cities500 and US.txt; keep the first
            if h[1][0] not in seen:
                seen.add(h[1][0])
                unique.append(h)
        hits = unique
        picked = hits[:n]
        if must and not any(r[10] == must for _, r in picked):
            picked += [h for h in hits if h[1][10] == must][:1]
        if not picked:
            sys.exit(f"no row for {name!r} in {cc}")
        for stem, r in picked:
            chosen.setdefault(int(r[0]), (stem, r))
    for gid in args.village:
        found = [(s, r) for s in COUNTRIES for r in by_stem[s] if int(r[0]) == gid]
        if not found:
            sys.exit(f"village {gid} not found in a country file")
        chosen.setdefault(gid, found[0])

    args.out.mkdir(parents=True, exist_ok=True)
    for stem in ("cities500", *COUNTRIES):
        lines = ["\t".join(r) for s, r in chosen.values() if s == stem]
        (args.out / f"{stem}.txt").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    ids = {str(g) for g in chosen}
    alt = ["\t".join(r) for r in _read(args.src, "alternateNamesV2") if r[1] in ids and r[2] in LANGUAGES]
    (args.out / "alternateNamesV2.txt").write_text("".join(f"{line}\n" for line in alt), encoding="utf-8")

    a1 = {f"{r[8]}.{r[10]}" for _, r in chosen.values()}
    a2 = {f"{r[8]}.{r[10]}.{r[11]}" for _, r in chosen.values()}
    for stem, keys in (("admin1CodesASCII", a1), ("admin2Codes", a2)):
        lines = ["\t".join(r) for r in _read(args.src, stem) if r[0] in keys]
        (args.out / f"{stem}.txt").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    isos = {r[8] for _, r in chosen.values()} | set(COUNTRIES)
    info = ["\t".join(r) for r in _read(args.src, "countryInfo") if r[0] in isos]
    (args.out / "countryInfo.txt").write_text("".join(f"{line}\n" for line in info), encoding="utf-8")
    print(f"wrote {len(chosen)} places, {len(alt)} alternate names to {args.out}")


if __name__ == "__main__":
    main()
