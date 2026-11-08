# Foundation 1B — Gazetteer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `geonamescache` with a bundled worldwide gazetteer that finds villages, matches
misspellings, Devanagari and Cyrillic, labels duplicates by region name, and is pinned by hash.

**Architecture:** `scripts/build_gazetteer.py` turns pinned GeoNames dumps into
`data/gazetteer.sqlite` (`places`, `names`, `meta`). `engine/geo.py` queries it on disk; its
public interface (`Place`, `find_places`, `get_place`) is unchanged apart from added region
names. Tests run against a small committed GeoNames extract built with the same code.

**Tech stack:** SQLite (stdlib), rapidfuzz, indic-transliteration.

---

### Task 1: Name folding

**Files:** create `samay/engine/names.py`; test `tests/test_names.py`.

- [ ] `fold(text)`: NFKC, casefold, Devanagari romanized (ITRANS → ASCII), accents stripped,
  punctuation removed, whitespace collapsed. Cyrillic stays Cyrillic.
- [ ] `skeleton(text)`: phonetic key of a folded Latin name — `oo→u`, `ee→i`, `w→v`, `sh→s`,
  `ph→f`, other `h` after a consonant dropped, vowels after the first letter dropped, doubled
  letters collapsed. Non-Latin text returns `""`.
- [ ] Tests: "Forlì"→"forli"; "पुणे"→"pune"; "Kolhapur", "Kolapur", "कोल्हापूर" share a
  skeleton; "Nagpur", "Nagpoor", "नागपुर" share a skeleton; "Київ" folds to itself.
- [ ] Commit.

### Task 2: Gazetteer builder

**Files:** create `scripts/build_gazetteer.py`, `samay/engine/gazetteer_build.py`,
`data/gazetteer.lock`; modify `.gitignore`.

- [ ] Builder reads GeoNames `cities500`, full country files (`GEONAMES_FULL_COUNTRIES`, default
  `IN,US,UA,IT`, feature classes P and A only), `admin1CodesASCII`, `admin2Codes`, and per-country
  alternate names filtered to languages `hi mr uk ru it en` and the empty language tag
  (excluding links, postcodes and airport codes). Names in other scripts are dropped.
- [ ] Rows without a timezone are skipped. Each name is stored with its `fold` key and
  `skeleton`; both are indexed.
- [ ] `meta` records the snapshot date and every source file's sha256. The script writes
  `data/gazetteer.lock` with the same plus the database's sha256. Downloads are cached in
  `data/geonames-src/` (ignored by git), so rebuilding from the same snapshot is reproducible.
- [ ] Commit.

### Task 3: Query engine

**Files:** modify `samay/engine/geo.py`, `samay/engine/paths.py`, `samay/service.py`,
`pyproject.toml` (drop geonamescache; add rapidfuzz, indic-transliteration).

- [ ] `Place` gains `admin1_name`, `admin2_name`; `label` is "Name, District, State, CC" with
  empty parts omitted.
- [ ] `find_places(query, limit=3)`: split an optional qualifier after the last comma (country
  code or region name); exact folded key → skeleton → rapidfuzz (WRatio ≥ 85) over names sharing
  the skeleton's first two letters; rank by match score, then feature (populated place first),
  then population; de-duplicate by place.
- [ ] Version stamp `gazetteer` = "geonames <snapshot> <db sha12>".
- [ ] Commit.

### Task 4: Test fixture and tests

**Files:** create `scripts/make_gazetteer_fixture.py`, `tests/fixtures/geonames-mini/*`,
`tests/conftest.py`, `tests/fixtures/birthplaces.yaml`, `tests/test_gazetteer.py`;
modify `tests/test_geo.py`.

- [ ] The fixture script copies selected rows (by geonameid) from the cached dumps into
  `tests/fixtures/geonames-mini/`; conftest builds a session database from it and points the
  engine at it, so CI never needs the full dump.
- [ ] Tests: exact, misspelled, Devanagari, Cyrillic and accent-free queries; region-name
  qualifier; region-labelled duplicates; village present in a full-country file but not in
  cities500; unknown name returns `[]`; builder writes meta and lock.
- [ ] `birthplaces.yaml` is a **seed list written by Claude** until the owner's real list
  replaces it; `test_hit_rate` runs against the real database when present and requires ≥ 95%.
- [ ] Commit.

### Task 5: Approximate place

**Files:** modify `samay/models.py`, `samay/service.py`, `samay/cli.py`; test in
`tests/test_service.py`.

- [ ] `BirthInput.approx_for: str | None` — the place the user originally named when they fall
  back to a nearby town. The service sets `Provenance.place_approximate` and an `approx_note`;
  the CLI gains `--approx-for`.
- [ ] Commit.
