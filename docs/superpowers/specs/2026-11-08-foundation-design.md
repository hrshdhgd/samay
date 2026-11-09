# Sub-project 1: Foundation — design

*2026-11-08. Status: hardened (brainstorm + crucible), approved.*

## Framing

The architecture — pure engine, report models, renderers, thin front ends — held under adversarial
review. What changed is scope and honesty: Foundation builds every *mechanism* the later
sub-projects need (provenance, version stamps, tradition profiles, time-standard overrides) but
ships only one validated-in-principle configuration, and nothing in it claims accuracy until it is
checked against a named reference.

## Context

samay is a self-contained Telegram bot that computes sidereal (Jyotish) charts from bundled data
and interprets them with a rule engine built from classical texts (see `HANDOFF.md`). Its users
are the owner and family, including elderly, non-technical relatives born anywhere in the world.
The goal is the most accurate possible representation of the tradition, built on cited research,
never on memory.

### Roadmap

| # | Sub-project | Depends on |
|---|---|---|
| **1** | **Foundation** (this spec) | — |
| 2 | Validation + historical time-standard research (India, Ukraine, USA, Italy) | 1 |
| 3 | ~~i18n: English, Hindi, Marathi~~ — dropped 2026-11-08: every user reads English. Revisit only if that changes. | — |
| 4 | Grounded free Q&A in English (the app's headline feature): answers only from computed chart facts and cited entries, shows the citation, says so when it has no sourced answer; no answers from the model's own knowledge | 2, 5 |
| 5 | Rule base: more yogas, conflict weighting, transit rules for `/today` | 2, 3 |
| 6 | Additional tradition profiles: true Chitrapaksha, Raman — each validated as added | 2 |
| 7 | KP system: Placidus cusps, star/sub-lords | 2 |
| 8 | Encryption at rest + backup/export — **hard gate before deploy** | 1 |
| 9 | Jataka PDF: panchanga, D1/D9 charts (South Indian default, North Indian option), dashas, yogas | 3, 5 |
| 10 | Ontology (OWL/SKOS/SHACL) — only if a concrete consumer exists by then | 5 |
| 11 | Deploy to the shared Oracle Ampere instance alongside stockbro | all required |

**Feedback without deploying:** after sub-projects 1 and 2, a CLI chart (and later a PDF) is shown
to one relative locally, and their reaction is recorded in the next spec.

### Decisions already made

- English only. No meaning text ships until its source is researched and cited (Q&A, /today and
  glossary answers included); until then the bot shows computed facts only.
- Private bot, chat-ID allowlist. Host Ollama shared with stockbro; no sidecar.
- Deploy via rsync + server-side build, like stockbro (sub-project 11).
- `pyproject.toml` + `uv` + `uv.lock`; `click` CLI; CLI is stateless.
- Users enter only the local clock time at the birthplace. samay derives the offset; the user is
  never asked for one. Converting inputs to IST was considered and rejected — it does not touch the
  real error, which is in reading the local clock.

## Definition of correct

- **Astronomy:** agreement with `swetest` (Swiss Ephemeris) and Jagannatha Hora — planets within
  1′, lagna within 3′, ayanamsa within 1″. These tools are reference oracles only, never
  dependencies.
- **Time resolution:** the time-standard table's cited primary sources (sub-project 2), falling
  back to tzdata.
- **Interpretation:** the active tradition profile's cited texts. Where texts disagree, the
  profile's documented conflict rule decides, and both readings are shown with citations.
- Until sub-project 2 passes, every report states that it is unvalidated.

## Architecture

```
samay/
  engine/        ephemeris.py vedic.py rules.py geo.py timestd.py profiles.py   pure, sync
  models.py      frozen dataclasses
  service.py     the only API front ends call
  render/text.py report → plain text; all user-facing wording lives in render/
  bot/           app.py (wiring), flow.py (guided conversation), handlers.py
  cli.py         click CLI (stateless)
  store.py       SQLite: users, drafts (bot only)
  narrate.py     optional Ollama rewording, off by default (bot only)
data/
  profiles/*.yaml          tradition profiles
  time_standards/*.yaml    curated offset overrides (schema now, researched entries in #2)
  gazetteer.sqlite         built artifact (not in git), sha256 pinned in repo
rules/  tests/  scripts/  .github/
```

Dependency direction: `bot`/`cli` → `service` → `engine`; `bot`/`cli` → `render`. The engine imports
nothing from the rest of samay. The CLI and the bot both go through the same `resolve_birth`.

### Models (`models.py`)

- `BirthInput(date_text, time_text, place_text, place_choice: str | None, fold: int | None, profile: str)`
  — exactly what the user typed and chose.
- `Provenance(offset, offset_source, confidence: Literal["verified","probable","tzdata","low"], place_approximate: bool, approx_note: str | None)`
- `ResolvedBirth(utc, place: Place, tz, provenance: Provenance)`
- `NeedsDisambiguation(kind: Literal["place","time"], options: list[Place] | list[datetime])` —
  up to 3 places (labelled with region and country), or the two UTC instants of an ambiguous time.
- `VersionStamp(git_sha, rules_hash, profile_id, profile_hash, timestd_version, tzdata_version, ephemeris_sha256, gazetteer_sha256)`
- `NatalReport(birth, chart, dashas, yogas, stamp, validated: bool)`
- `TodayReport(natal, sky, now, current_dasha, facts, stamp)`

### Service (`service.py`, synchronous)

- `resolve_birth(BirthInput) -> ResolvedBirth | NeedsDisambiguation`
- `natal_report(ResolvedBirth, profile) -> NatalReport` — `lru_cache(maxsize=64)` keyed on
  `(utc, latitude, longitude, profile_id)`. Data versions are fixed per process; every deploy
  restarts the process, so a cached result cannot outlive its data.
- `today_report(ResolvedBirth, profile, now)` — `now` always injected.
- `warm()`, `data_info() -> VersionStamp`.
- Typed errors: `PlaceNotFound`, `NonexistentTime`, `OutOfEphemerisRange`, `EphemerisMissing`,
  `UnknownProfile`, `UnsupportedLatitude`. Ambiguity is a return value, not an exception.

## Time standards (`engine/timestd.py`)

- `data/time_standards/<country>.yaml` entries: `region` (GeoNames country + admin1/admin2),
  `from`/`to` dates, `offset`, `name` (e.g. "Bombay Time"), `confidence`, and `source` with
  `text`, `locus`, `verified`.
- Resolution order: matching curated entry → tzdata.
- Foundation ships the schema, loader, matcher and tests, with **no unverified historical entries**.
  Entries are added only in sub-project 2, from primary sources (Gazette notifications, government
  orders, railway time tables, contemporary newspapers).
- Without a curated entry, confidence comes from the era: `tzdata` for 1970 onwards; `low` before
  1970, and `low` with an explicit warning for India before 1956, where tzdata is known to model
  the whole country as one zone.
- Every chart shows the offset used, its source and its confidence.
- DST overlaps (births abroad) still ask "first or second 01:30?" — a question about the clock
  reading, not the offset. Nonexistent local times are rejected with an explanation.

## Tradition profiles (`engine/profiles.py`)

- `data/profiles/<id>.yaml`: ayanamsa, node (mean/true), house system, dasha year length,
  calculation method (drik), rule schools included, conflict rule, `validated` flag, citations for
  every formula and constant.
- Rules are filtered by the profile's schools (the existing `school` field in `rules/*.yaml`).
- Every report and stamp records the profile. Each user's stored choices include their profile.
- **Foundation ships one profile:** `parashari-lahiri` — Lahiri (mean), mean node, whole-sign
  houses, 365.25-day dasha year. Other profiles arrive in sub-projects 6 and 7.
- Drik vs siddhantic calculation is recorded as an open decision for sub-project 2.

## Places (`engine/geo.py`)

- **Data:** GeoNames `cities500` worldwide, plus full country files for `GEONAMES_FULL_COUNTRIES`
  (default `IN,US,UA,IT`) filtered to feature classes P and A, plus `alternateNamesV2` filtered to
  `hi, mr, uk, ru, it, en`. Licence CC-BY; attribution in README and `/help`.
- **Build:** `scripts/build-gazetteer.py` downloads the files once, records their sha256 and the
  snapshot date, and writes `data/gazetteer.sqlite` (names, alternate names, admin1/admin2,
  country, coordinates, population, timezone). The artifact's sha256 is committed in
  `data/gazetteer.lock`. The Dockerfile only copies the artifact and verifies the hash; nothing is
  downloaded or built on the server. Refreshing is a deliberate step in `update-data.sh`.
- **Matching:** Devanagari input is romanized offline (`indic-transliteration`); Cyrillic and
  Latin are matched directly against alternate names. All names are folded (case, accents,
  aspirates, vowel length, common spelling variants such as "oo" → "u"), then candidates are
  ranked with `rapidfuzz` and population.
- **Duplicates:** up to 3 buttons labelled "Name, Region, Country".
- **Not found:** the bot asks for the nearest town or the district; provenance records
  "approximate: nearest X, about N km", and the chart says so.
- **Test fixture:** the owner supplies 30–50 real family birthplaces, written the way family
  members would actually type them (misspellings, Devanagari, Cyrillic). Target hit rate ≥ 95%.
  CI uses a small committed fixture gazetteer; the full hit-rate test runs locally against the
  real artifact.

## Bot (`bot/`)

- **Allowlist:** `ALLOWED_CHAT_IDS` → `filters.Chat` on every handler; empty → refuse to start;
  non-allowlisted chats get no reply.
- **Guided conversation** (PTB `ConversationHandler`, no LLM): one plain question per step, buttons
  wherever possible, a permanent Menu keyboard, and a Start over button on every step. Slash
  commands remain as shortcuts: `/start /help /birth /chart /dasha /today /forget`.
- **Robustness:** every callback carries a step token; stale or unknown taps get a friendly
  restart; typed text where a button was expected re-asks the same question.
- **Drafts:** half-finished entries are saved in the `drafts` table and resume after a restart.
  Drafts expire after 30 minutes and are deleted.
- All service calls via `asyncio.to_thread`. `post_init` warms data and logs the version stamp;
  `post_shutdown` closes the narrate client.
- Error handler logs chat ID and error type only — never birth data. `httpx` and `telegram`
  loggers are set to WARNING (their INFO logs include the bot token in URLs).
- `allowed_updates=[MESSAGE, CALLBACK_QUERY]`.

## CLI (`cli.py`, click, stateless)

- `samay chart --date YYYY-MM-DD --time HH:MM --place "…" [--choice ID] [--fold 0|1] [--profile ID]`
- `samay dasha …` · `samay today … [--now ISO8601]` · `samay data-info`
- Ambiguity: exit code 2, options listed on stderr; never prompts.

## Store (`store.py`)

- `users`: raw `BirthInput` fields as typed, place choice, fold, profile. Every read re-resolves
  from the raw input, so data corrections apply automatically.
- `drafts`: in-progress conversation state with expiry.
- Schema versioned with `PRAGMA user_version` and an ordered list of migrations.
- `/forget` deletes the user's row and any draft.

## Narration (`narrate.py`)

Off by default (`OLLAMA_URL` unset → the template is the reading). When enabled: one shared
`httpx.AsyncClient`, `OLLAMA_MODEL` default `llama3.2:3b`, 20 s timeout, any failure → template,
no `keep_alive` override. The LLM only rewords facts the engine computed.

## Packaging, container, CI

- `pyproject.toml` (Python 3.12; deps: skyfield, python-telegram-bot 21, pyyaml, tzdata, httpx,
  click, rapidfuzz, indic-transliteration; dev: pytest, ruff) and `uv.lock`. `requirements.txt`
  removed; `geonamescache` removed.
- Dockerfile: `uv sync --frozen --no-dev`; `ADD --checksum=sha256:…` for `de440s.bsp` (hash shared
  with `scripts/fetch-ephemeris.sh`); copies and verifies `gazetteer.sqlite`;
  `ENV PYTHONTZPATH=""`; `ARG GIT_SHA`; non-root user.
- `docker-compose.yml`: no Ollama sidecar; `mem_limit: 512m`, `cpus: 1.0`. Server wiring is
  sub-project 11.
- CI (`.github/workflows/test.yml`, amd64): `uv sync --frozen`, cached checksum-verified
  ephemeris, `uv run ruff check`, `uv run pytest`.
- arm64: `scripts/test-arm64.sh` runs the suite inside the built image locally; required before
  each deploy.
- Data freshness: `samay data-info`; `scripts/update-data.sh` (tzdata, skyfield, gazetteer
  refresh, then tests); Dependabot (`uv`, monthly).

## Testing

- Existing unit tests move to `engine/` imports with assertions unchanged.
- **Golden charts:** 5 charts (including a southern-hemisphere birth, a DST-boundary birth and a
  1950s Indian birth) with expected values from `swetest`, produced by a separate script and
  committed as fixture values, checked within the tolerances above.
- Time standards: schema validation; curated-entry precedence over tzdata (using a test-only
  fixture entry); confidence by era; India-before-1956 warning.
- DST: `America/New_York` 2021-11-07 01:30 (ambiguous), 2021-03-14 02:30 (nonexistent),
  `Asia/Kolkata` control.
- Places: fixture gazetteer; folding and fuzzy matching ("Kolapur" → Kolhapur, "पुणे" → Pune,
  "Kiev" → Kyiv, "Forli" → Forlì); region-labelled duplicates; approximate fallback; the owner's
  hit-rate fixture locally.
- Profiles: loader, rule filtering by school, profile recorded in the stamp, unknown profile error.
- Service: report structure for a fixed input and `now`; cache hit; 1800 birth year →
  `OutOfEphemerisRange`.
- Retrograde: a known Mercury station date.
- Bot flow: guided-flow transitions, stale-tap recovery, draft resume and expiry, empty allowlist
  refuses to start.
- CLI: `CliRunner` happy path, ambiguity → exit 2, malformed date.
- Narrate: disabled by default; `httpx.MockTransport` timeout and 500 → template.
- Logs: error-handler records contain no birth data; `httpx` logger level is WARNING.

## Done when

1. `uv run pytest` and `uv run ruff check` pass locally and in CI; `scripts/test-arm64.sh` passes.
2. The 5 golden charts are within tolerance.
3. The owner's birthplace fixture reaches ≥ 95%.
4. `samay chart --date 1990-08-15 --time 14:30 --place "Pune"` prints a chart with provenance,
   profile and an "unvalidated" note.
5. The bot runs locally with the owner allowlisted and completes the guided flow, including a DST
   disambiguation and a restart mid-flow.
6. `docker build` succeeds locally on arm64.

## Grounded Q&A (sub-project 4): decisions so far

Free Q&A is the app's headline feature. It is English-only and grounded:

- **Entries:** plain-English paraphrases of the public-domain Sanskrit texts (BPHS, Brihat Jataka,
  Saravali, Phaladeepika, Jataka Parijata), each citing chapter and verse.
- **Verification levels**, stored per entry and shown next to the citation: `unchecked` (draft,
  never shown as an answer), `translation-checked` (compared with a named public-domain English
  translation, with who checked and when), `sanskrit-checked` (read against the verse by a
  Sanskrit reader). No family member reads Sanskrit, so entries start at `translation-checked`;
  a scholar upgrades the most-used ones later.
- **The model only sorts the question** into a topic (for example `topic: dasha, planet: saturn`).
  samay writes the answer from checked entries, word for word, plus computed chart facts, with
  citations. The model writes none of the answer.
- **No sourced answer:** the bot says so and shows the related computed facts.
- **Unanswered questions:** only the sorted topic and a count are stored, never the wording or a
  chat id. `samay research-queue` lists the most-wanted topics.
- **Tooling:** word-by-word breakdown aids for reviewers live in a `research` dependency group
  that is not installed in the Docker image or in CI. Experiments live in `research/` with a
  `program.md` and `results.tsv`. Machine output is an aid, never the check.

### Verse display and sources (decided 2026-11-09)

- **Display:** answers show the English paraphrase first, with a **Show Sanskrit** button that swaps
  in the Devanagari verse (plus Roman letters) in place, and an **English** button that swaps back.
  Devanagari is sent as Telegram text, never drawn into images.
- **Each entry stores:** Devanagari verse, Roman-letter form, English paraphrase, citation (text,
  chapter, verse), verification level, and who checked it and when. A verse is shown only if its
  text was checked against a second copy; a mistyped verse under a citation is worse than none.
- **Start with Brihat Jataka.** N. Chidambaram Iyer's 1885 English translation appears to be
  public domain (Wellcome Collection and HathiTrust list it so; to be confirmed when the entries
  are written), which makes the `translation-checked` level possible. For BPHS no clearly
  public-domain English translation was found (one Internet Archive edition is CC BY-ND, which
  bars derivatives), so BPHS entries wait for a checkable source.
- **Open:** a clean, licensed source for typed Devanagari verse text. Internet Archive scans are
  page images that would need OCR, and nobody in the family can proofread Sanskrit.

## Known risks

- Plaintext birth data in `users` and `drafts` until sub-project 8. Acceptable while local;
  sub-project 8 is a hard gate before deploy.
- No backup/export of the store until sub-project 8.
- Monthly Dependabot may cause churn; switch to quarterly if it does.
- Re-resolution applies data corrections automatically, but readings already given are not
  migrated or annotated; version stamps make them reproducible.
- 30–50 birthplaces is a small sample; extend the fixture as real usage reveals misses.
- Feedback before deploy is limited to local demos.
