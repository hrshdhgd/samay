# Foundation 1A — Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the draft into an installable package with a pure engine, frozen report models,
tradition profiles, a time-standard override layer, version stamps, a service layer, a text
renderer, a stateless CLI and golden-chart checks.

**Architecture:** `cli` → `service` → `engine`; `cli` → `render`. The engine imports nothing from
the rest of samay. Places still come from `geonamescache` behind `engine.geo.find_places`; plan 1B
replaces the backend without changing that interface. The Telegram bot is out of scope here
(plan 1C rewrites it), so the draft `bot.py` and `db.py` are removed; `narrate.py` is kept.

**Tech stack:** Python 3.12, uv, Skyfield + DE440s, PyYAML, tzdata, click, pytest, ruff.
Reference oracle (dev only, never a dependency): pyswisseph via `uv run --with`.

Spec: `docs/superpowers/specs/2026-11-08-foundation-design.md`.

Code for each task lives in the repo at the task's commit. This plan lists files, interfaces and
test cases so a reviewer can check the commit against it.

---

### Task 1: Packaging with uv

**Files:** create `pyproject.toml`, `uv.lock`; delete `requirements.txt`; modify `.gitignore`.

- [ ] `pyproject.toml`: project `samay`, Python `>=3.12,<3.13`; deps skyfield, python-telegram-bot
  `>=21,<22`, pyyaml, tzdata, httpx, click, geonamescache; dev group pytest, ruff; script
  `samay = "samay.cli:cli"`; hatchling build with `packages = ["samay"]`; ruff line length 110.
- [ ] `uv sync` succeeds; `uv run pytest -q` still runs the draft tests (10 pass, 1 skip).
- [ ] Commit.

### Task 2: Ephemeris fetch script

**Files:** create `scripts/fetch-ephemeris.sh`.

- [ ] Script downloads `de440s.bsp` to `data/` (or `$1`) and verifies sha256 against the constant
  in the script; exits non-zero on mismatch. Hash recorded from the first download.
- [ ] `uv run pytest -q` → the smoke test now runs and passes.
- [ ] Commit.

### Task 3: Move the engine and add typed errors

**Files:** create `samay/engine/{__init__,paths,errors}.py`; move `ephemeris.py vedic.py rules.py
geo.py` into `samay/engine/`; update `tests/test_core.py` imports only.

- [ ] `engine/paths.py`: `ROOT`, `DATA_DIR` (`SAMAY_DATA_DIR`), `RULES_DIR` (`SAMAY_RULES_DIR`),
  `EPHEMERIS_PATH` (`SAMAY_EPHEMERIS`).
- [ ] `engine/errors.py`: `SamayError` base; `InvalidInput`, `PlaceNotFound`, `NonexistentTime`,
  `OutOfEphemerisRange`, `EphemerisMissing`, `UnknownProfile`, `UnsupportedLatitude`.
- [ ] Draft tests pass with unchanged assertions.
- [ ] Commit.

### Task 4: Ephemeris hardening

**Files:** modify `samay/engine/ephemeris.py`; test `tests/test_ephemeris.py`.

- [ ] Tests: naive datetime → `ValueError`; 1800-01-01 → `OutOfEphemerisRange`; latitude 70 →
  `UnsupportedLatitude`; missing kernel → `EphemerisMissing`; Mercury retrograde on 2023-04-25
  and direct on 2023-03-01 (ephemeris required).
- [ ] `compute_chart(utc, lat, lon, ayanamsa="lahiri_mean", node="mean")`; retrograde from the
  sign of motion between t−1h and t+1h; `AYANAMSAS` / `NODES` registries; range
  1849-12-27..2150-01-21; |lat| > 66.5 rejected.
- [ ] Commit.

### Task 5: Tradition profiles

**Files:** create `samay/engine/profiles.py`, `data/profiles/parashari-lahiri.yaml`;
modify `samay/engine/vedic.py` (`year_days` parameter), `samay/engine/rules.py`
(`load_rules(directory, schools)`); test `tests/test_profiles.py`.

- [ ] `Profile` frozen dataclass: `id, name, ayanamsa, node, houses, dasha_year_days, method,
  schools, conflict_rule, validated, citations, sha256`.
- [ ] `load_profile(id)` validates every field against supported values; unknown id →
  `UnknownProfile`; unsupported value → `ValueError` naming the field.
- [ ] Tests: default profile loads, `validated is False`, hash stable; unknown id raises; a
  profile with `houses: placidus` is rejected; rules filtered by school; `vimshottari` honours
  `year_days=360`.
- [ ] Commit.

### Task 6: Places and time standards

**Files:** modify `samay/engine/geo.py`; create `samay/engine/timestd.py`,
`data/time_standards/README.md`; tests `tests/test_geo.py`, `tests/test_timestd.py`,
`tests/fixtures/time_standards/test.yaml`.

- [ ] `Place(id, name, country, admin1, admin2, latitude, longitude, tz, population)`;
  `find_places(query, limit=3) -> list[Place]` ranked by population, optional `, CC` filter,
  index built once.
- [ ] `timestd`: `StandardEntry`, `load_standards(directory)` with schema validation,
  `resolve_local_time(local, place, fold, entries) -> TimeResolution | AmbiguousTime`.
  Precedence: most specific curated entry, then tzdata. Nonexistent → `NonexistentTime`.
  Confidence: entry's own; else `tzdata` from 1970, `low` before; India before 1956 adds a warning.
- [ ] Tests: Pune resolves; "Aurangabad, IN" returns ≥ 2 places in different admin1 regions;
  unknown place → empty list; NY 2021-11-07 01:30 ambiguous with two instants one hour apart;
  fold 0/1 picks each; NY 2021-03-14 02:30 → `NonexistentTime`; Kolkata 1990 → +5:30 `tzdata`;
  Pune 1952 → `low` with warning; fixture curated entry overrides tzdata and carries its source;
  malformed entry rejected.
- [ ] Commit.

### Task 7: Models, version stamp, service

**Files:** create `samay/models.py`, `samay/service.py`; test `tests/test_service.py`.

- [ ] Models per spec: `BirthInput`, `Provenance`, `ResolvedBirth`, `NeedsDisambiguation`,
  `VersionStamp`, `NatalReport`, `TodayReport(natal, sky, now, current_dasha, transit_houses)`.
- [ ] Service: `parse_date`/`parse_time` (accept `YYYY-MM-DD` and `DD-MM-YYYY`, `HH:MM`);
  `resolve_birth`; `natal_report` (cached); `today_report`; `warm`; `data_info`.
- [ ] Tests: Pune 1990-08-15 14:30 → 09:00 UTC with provenance; "Aurangabad, IN" →
  `NeedsDisambiguation("place")`, then resolves with `place_choice`; NY ambiguous time →
  `NeedsDisambiguation("time")`; bad date → `InvalidInput`; unknown place → `PlaceNotFound`;
  report carries stamp + profile, `validated is False`; second call is a cache hit;
  today_report uses the injected `now`.
- [ ] Commit.

### Task 8: Text renderer

**Files:** create `samay/render/{__init__,text}.py`; test `tests/test_render.py`.

- [ ] `render_chart`, `render_dasha(report, now)`, `render_today`, `render_options`; every
  report ends with the provenance line (offset, source, confidence, warning), profile with an
  "unvalidated" note, short stamp, disclaimer.
- [ ] Tests: chart text contains lagna, all nine grahas, "unvalidated", the offset, the
  disclaimer; warning appears for a 1952 Pune birth.
- [ ] Commit.

### Task 9: CLI

**Files:** create `samay/cli.py`; delete `samay/bot.py`, `samay/db.py`; test `tests/test_cli.py`.

- [ ] `samay chart|dasha|today|data-info`; birth options `--date --time --place --choice --fold
  --profile`; `today --now`. Ambiguity → options on stderr, exit 2. `SamayError` → message on
  stderr, exit 1.
- [ ] Tests (`CliRunner`): chart happy path; ambiguity exit 2 lists `--choice` ids; malformed
  date exit 1; `data-info` prints the stamp.
- [ ] Commit.

### Task 10: Golden charts

**Files:** create `scripts/golden_charts.py`, `tests/fixtures/golden_charts.json`,
`tests/test_golden.py`.

- [ ] Script (run with `uv run --with pyswisseph python scripts/golden_charts.py`) computes 5
  charts with Swiss Ephemeris (Moshier, Lahiri, mean node) and writes expected sidereal
  longitudes, ascendant and ayanamsa.
- [ ] Test compares samay within tolerance: planets 1′, lagna 3′, ayanamsa 1″. Any failure is a
  real finding to report, not a tolerance to loosen.
- [ ] Commit.

### Task 11: Docs

**Files:** modify `README.md`, `CLAUDE.md`, `.env.example`.

- [ ] Commands use `uv`; `.env.example` gains `ALLOWED_CHAT_IDS`; narration documented as off by
  default.
- [ ] `uv run ruff check` and `uv run pytest -q` clean. Commit.

## Following plans

1B Gazetteer, 1C Bot, 1D Ship — each written after the previous plan lands.
