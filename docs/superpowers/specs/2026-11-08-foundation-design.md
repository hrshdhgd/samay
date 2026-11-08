# Sub-project 1: Foundation — design

*2026-11-08. Status: draft for review.*

## Context

samay is a self-contained Telegram bot that computes sidereal (Jyotish) charts from bundled data
and interprets them with a rule engine built from classical texts (see `HANDOFF.md`). The current
code is a rough draft (~830 lines). The product is being built out locally in eight sub-projects,
each with its own spec → plan → implementation cycle, and deployed last:

| # | Sub-project | Depends on |
|---|---|---|
| **1** | **Foundation: service layer, hardening, CLI, data freshness** (this spec) | — |
| 2 | Validation: reference-chart fixtures (Jagannatha Hora / swetest) | 1 |
| 3 | i18n: English, Hindi, Marathi | 1 |
| 4 | Rule base: more yogas, weighting, transit rules for `/today` | 2, 3 |
| 5 | Privacy: encryption at rest | 1 |
| 6 | Jataka PDF: panchanga, D1/D9 charts (South Indian default, North Indian option), dashas, yogas | 3, 4 |
| 7 | Ontology: OWL/SKOS/SHACL export | 4 |
| 8 | Deploy to the shared Oracle Ampere instance alongside stockbro | all |

### Decisions already made

- **Audience:** private bot (owner + family/friends), enforced by a chat-ID allowlist.
- **LLM:** the host's existing Ollama (shared with stockbro), no sidecar. Default `llama3.2:3b`.
- **Deploy model (sub-project 8):** rsync from the Mac, build on the server, like stockbro.
- **Packaging:** `pyproject.toml` + `uv` + `uv.lock`. CLI via `click` (matches stockbro's `bro`).
- **CLI:** stateless — birth data passed as arguments; never touches the user DB.
- **Architecture:** pure engine → report model → renderers; front ends are thin adapters.
- **Data updates:** Dependabot PRs against `uv.lock`, gated by CI.

## Goals

1. A service layer every front end (bot, CLI, later PDF) calls, returning plain report objects.
2. Fix the draft's correctness/robustness issues (event-loop blocking, DST ambiguity, no access
   control, unpinned ephemeris, coarse retrograde check).
3. Make it efficient on a shared 4-core ARM box (cached natal charts, indexed place lookup,
   warm start, short LLM timeout).
4. A visible, testable process for keeping time-zone and other bundled data current.

## Non-goals

Accuracy validation against reference software (#2), translations (#3), new rules (#4),
encryption (#5), PDF (#6), ontology (#7), server deployment (#8). Astronomy formulas
(ayanamsa, node, houses) do not change here except the retrograde check.

## Architecture

```
samay/
  engine/        ephemeris.py vedic.py rules.py geo.py   pure, sync; moved from samay/
  models.py      frozen dataclasses
  service.py     the only API front ends call
  render/text.py report → plain text; all user-facing wording lives in render/
  bot.py         async Telegram adapter
  cli.py         click CLI (stateless)
  store.py       user profiles, SQLite (bot only)
  narrate.py     optional Ollama rewording (bot only)
rules/  tests/  scripts/  .github/
```

Dependency direction: `bot`/`cli` → `service` → `engine`; `bot`/`cli` → `render`. The engine
imports nothing from the rest of samay. Narration stays outside the service so the "LLM only
rewords computed facts" rule lives in one place.

### Models (`models.py`)

- `BirthInput(local: datetime, place_query: str, fold: int | None = None)` — `local` is naive.
- `ResolvedBirth(utc: datetime, place: Place, tz: str)` — `utc` is timezone-aware UTC.
- `NeedsDisambiguation(kind: Literal["place", "time"], options: list[Place] | list[datetime])` —
  up to 3 places (most populous first), or the two UTC instants of an ambiguous local time.
- `NatalReport(birth: ResolvedBirth, chart: Chart, dashas: list[Period], yogas: list[Rule])`
- `TodayReport(natal: NatalReport, sky: Chart, now: datetime, current_dasha: tuple[Period, Period] | None, facts: list[str])`

### Service (`service.py`, synchronous)

- `resolve_birth(BirthInput) -> ResolvedBirth | NeedsDisambiguation`
- `natal_report(ResolvedBirth) -> NatalReport` — `lru_cache(maxsize=64)` keyed on
  `(utc, latitude, longitude)`.
- `today_report(ResolvedBirth, now: datetime) -> TodayReport` — `now` is always injected.
- `warm() -> None` — loads kernel, timescale, city index and rules.
- `data_info() -> DataInfo` — versions of tzdata, skyfield, geonamescache; ephemeris sha256 and
  valid date range; rule count.
- Typed errors: `PlaceNotFound`, `NonexistentTime`, `OutOfEphemerisRange`, `EphemerisMissing`.
  Ambiguity is a return value, not an exception.

### Store (`store.py`)

SQLite `users` table as today, with schema versioning via `PRAGMA user_version` and an ordered
list of migrations, so later sub-projects can add columns (language, chart style, encrypted
fields) without manual SQL. `/forget` deletes the row.

## Hardening and front ends

### `bot.py`

- **Allowlist:** `ALLOWED_CHAT_IDS` (comma-separated ints) → `filters.Chat(...)` on every handler.
  Empty or unset → refuse to start. Non-allowlisted chats get no reply.
- All service calls via `await asyncio.to_thread(...)`.
- `post_init` calls `service.warm()` and logs `data_info()` plus `GIT_SHA`;
  `post_shutdown` closes the narrate client.
- Error handler logs traceback with chat ID and error type only (never birth data) and replies
  with a generic message.
- `allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY]`.
- Disambiguation via inline keyboards: up to 3 places, or "first/second HH:MM" for a DST overlap.
  Nonexistent local times (skipped by DST) are rejected with an explanation.
- Commands: `/start` `/help` `/birth` `/chart` `/dasha` `/today` `/forget` (same as draft).

### `cli.py` (click, entry point `samay = "samay.cli:cli"`)

- `samay chart --date YYYY-MM-DD --time HH:MM --place "City[, CC]" [--fold 0|1]`
- `samay dasha …` · `samay today … [--now ISO8601]` · `samay data-info`
- Ambiguous input: exit code 2, options listed on stderr. Never prompts interactively.

### `engine/geo.py`

- City index built once (`lru_cache`): casefolded name and alternate names → list of cities.
- `local_to_utc(local, tz, fold)` detects ambiguous/nonexistent times by comparing `fold=0` and
  `fold=1` round-trips and returns a result type instead of silently picking one.

### `engine/ephemeris.py`

- Retrograde from the sign of longitude change over ±1 hour (was +6 hours forward-only).
- Dates outside the kernel's range raise `OutOfEphemerisRange`.

### `narrate.py`

- One module-level `httpx.AsyncClient`. `OLLAMA_URL` empty → template only.
- `OLLAMA_MODEL` default `llama3.2:3b`; 20 s timeout; any failure → template. No `keep_alive`
  override (Ollama's default unloads idle models, which matters on the shared box).

### Packaging and container

- `pyproject.toml` (Python 3.12, deps as today plus `click`; dev group: `pytest`, `ruff`) and
  `uv.lock`. `requirements.txt` is removed.
- Dockerfile: `uv sync --frozen --no-dev`; `ADD --checksum=sha256:…` for `de440s.bsp`, using the
  hash recorded in `scripts/fetch-ephemeris.sh` on first download (single source of truth);
  `ENV PYTHONTZPATH=""` so `zoneinfo` uses only the pinned `tzdata` package;
  `ARG GIT_SHA` → env; non-root user kept.
- `docker-compose.yml`: remove the `ollama` sidecar and `llm` profile; add `mem_limit: 512m`,
  `cpus: 1.0`; `.env.example` gains `ALLOWED_CHAT_IDS` and documents `OLLAMA_URL`/`OLLAMA_MODEL`.
  Server-specific wiring (`172.17.0.1`) is sub-project 8.

## Data freshness

| Data | Source | Staleness risk |
|---|---|---|
| Time zones / DST history | `tzdata` (IANA) | High — historical corrections move the lagna |
| Leap seconds / ΔT | built into `skyfield` | Negligible for charts |
| Ephemeris | `de440s.bsp` (1849–2150) | None in range; out-of-range is an explicit error |
| Cities | `geonamescache` | Low |
| Rules | `rules/*.yaml` | Versioned in git |

- `samay data-info` and the bot's startup log show exactly which data versions are in use.
- `scripts/update-data.sh`: `uv lock --upgrade-package tzdata --upgrade-package skyfield
  --upgrade-package geonamescache`, then `uv run pytest`.
- `.github/dependabot.yml`: `uv` ecosystem, monthly.
- `.github/workflows/test.yml`: on push/PR, `uv sync --frozen`, fetch the ephemeris (cached,
  checksum-verified via `scripts/fetch-ephemeris.sh`), `uv run ruff check`, `uv run pytest`.
  Runs on amd64; local development covers arm64.
- Once sub-project 2 lands, its reference-chart fixtures are the regression gate that catches a
  tzdata update changing a historical offset.

## Testing

- Existing unit tests move to `engine/` imports with assertions unchanged.
- `scripts/fetch-ephemeris.sh` downloads and sha256-verifies `de440s.bsp`; ephemeris-dependent
  tests skip when it is absent.
- Geo: index results equal the old linear scan on a sample; "Pune, IN" resolves; an ambiguous
  name yields options.
- DST: `America/New_York` 2021-11-07 01:30 (ambiguous), 2021-03-14 02:30 (nonexistent),
  `Asia/Kolkata` as the no-DST control.
- Service: report structure for a fixed input and `now`; a repeat call is a cache hit;
  a 1800 birth year raises `OutOfEphemerisRange`.
- Retrograde: a known Mercury station date (ephemeris required).
- CLI: `CliRunner` happy path, ambiguous → exit 2 with options, malformed date.
- Bot: empty `ALLOWED_CHAT_IDS` refuses to start.
- Narrate: `httpx.MockTransport` timeout and HTTP 500 both fall back to the template.
- Logs: a test asserts the error handler's log record contains no birth date/time.

## Error handling

Engine and service raise the typed errors above. Each front end maps them to one user-facing
message (bot reply / CLI stderr + non-zero exit). Raw exceptions never reach users. Logs never
contain birth data.

## Done when

1. `uv run pytest` passes with the ephemeris fetched, and `uv run ruff check` is clean.
2. `samay chart --date 1990-08-15 --time 14:30 --place "Pune, IN"` prints a full chart.
3. The bot runs locally with the owner's chat ID allowlisted and handles all seven commands,
   including a DST disambiguation flow.
4. `docker build` succeeds locally on arm64 with the pinned ephemeris.
5. CI is green on GitHub (after the repo is pushed).
