# samay — project handoff

*Discussion record, 8 Nov 2026. Read this first, then `CLAUDE.md`.*

samay (समय, "time") is a **self-contained Telegram bot** that computes sidereal (Jyotish) charts
from bundled planetary data and interprets them with a **rule engine built from classical
Indian texts**. Every rule cites its source. A local LLM can optionally reword the output.

---

## 1. How we got here (summary of the discussion)

### 1.1 "Can a data-driven app make accurate horoscope predictions?"
- **The astronomy is the easy part.** Planetary positions from NASA JPL ephemerides (via
  Skyfield or Swiss Ephemeris) are accurate to arc-seconds.
- **Predictions are the hard part, and not an engineering problem.** Controlled tests haven't
  found predictive validity in astrology: Carlson's double-blind study (*Nature*, 1985), the
  time-twin studies, and Hartmann/Reuter/Nyborg (2006, >15k people, no sun-sign effect on
  personality/IQ). Exact inputs don't make the interpretive link valid.
- **Decision:** samay is positioned as **traditional interpretation for reflection and
  entertainment, computed exactly and attributed honestly**. It doesn't claim to forecast
  accurately. Every reading carries a disclaimer.

### 1.2 How existing apps do it
Co-Star (the best-documented one) works like this: birth data → NASA JPL positions → transits
against the natal chart → a rules table that gives each configuration an astrological meaning
→ a library of **short snippets written by people** (writers and astrologers) chosen for each
configuration. Since 2023 there's also an LLM Q&A feature ("The Void"). Others (The Pattern,
CHANI, Sanctuary) lean on human writers or live astrologers.
Why these apps *feel* accurate: the Barnum/Forer effect, confirmation bias, a blunt tone,
well-timed push notifications, and the "NASA data" label.
**samay's edge isn't accuracy.** It's voice, the Telegram format, Jyotish depth, and
transparency about sources.

### 1.3 Idea considered and parked: train on famous people's life events
Using celebrity birth dates and biographies as training data was considered and **parked**:
- It's been tried: Gauquelin's "Mars effect" (disputed, likely selection bias), large
  birth-date studies, and time twins all came back null.
- Problems: famous people are a biased sample; biographical event data is noisy; a chart has
  hundreds of features against tens of thousands of people, so a model overfits; and there are
  real **seasonal confounders** (the relative-age effect in sports, birth-month disease
  associations, Tatonetti/Columbia 2015) that a naive model would credit to the planets.
- If it's ever revived, the protocol in §6 applies.

### 1.4 Chosen approach: a rule engine from classical texts
- Encode rules from **Brihat Parashara Hora Shastra (BPHS)**, Varahamihira's **Brihat Jataka**,
  **Saravali**, **Phaladeepika** and **Jataka Parijata**.
- The Sanskrit originals are public domain; most English translations (e.g. Santhanam's BPHS)
  are **under copyright**. So rule effects are **paraphrased in our own words** and cite the
  verse.
- The rules are **centuries old, so effectively pre-registered hypotheses**. That makes a later
  "predictive" phase testable without the overfitting problem (§6).
- The hard part is **conflict resolution**: most charts trigger dozens of yogas, often
  contradictory. Weighting (e.g. shadbala) has to be explicit and documented, and it's where
  arbitrariness creeps in.
- This fits an ontology approach well (planets, houses, signs, nakshatras, dashas and yogas as
  an OWL/SKOS model; rules in SHACL/SWRL/Datalog; provenance per rule). For v1 we use YAML plus
  a small Python evaluator, with the ontology as a later step.

### 1.5 Hard requirement: portable, self-contained, no anonymous servers
- **No third-party compute or API at runtime.** Explicitly rejected: VedAstro (calculations
  run on its cloud server), PyJHora (AGPL plus a PyQt6 dependency), Swiss Ephemeris (AGPL or a
  paid licence).
- Deployable with `docker compose up -d` on **Oracle Cloud (Ampere arm64)**, any VPS, a
  Raspberry Pi or a laptop.
- The **only** outbound connection is Telegram's Bot API. Long polling means no public port,
  domain or TLS.
- Name: **samay**.

---

## 2. Architecture

```
Telegram ⇄ (long polling) ⇄ samay.bot
                               │
        ┌──────────────────────┼─────────────────────────┐
        ▼                      ▼                         ▼
  samay.geo              samay.ephemeris            samay.db (SQLite)
  GeoNames (bundled)     Skyfield + JPL DE440s      users' birth data
  + IANA tzdata          (bundled, offline)
        │                      │
        └────────► samay.vedic (signs, nakshatras, houses, D9, Vimshottari)
                               │
                       samay.rules ◄── rules/*.yaml (with source provenance)
                               │
                       samay.narrate → template, or local Ollama (optional sidecar)
```

| Concern | Choice | Licence | Notes |
|---|---|---|---|
| Ephemeris | Skyfield + JPL **DE440s** (1849–2150) | MIT / public domain | Baked into the image at build time |
| Zodiac | Sidereal, **Lahiri** ayanamsa | — | Our own formula, Swiss-Ephemeris reference epoch; ≈23.857° at J2000 |
| Nodes | **Mean** node (Meeus 47.7) | — | True node = TODO option |
| Houses | **Whole sign** from lagna | — | Standard in Parashari; others = later |
| Ascendant | Meeus 14.2 using GAST | — | Breaks near polar latitudes (acceptable) |
| Geocoding | `geonamescache` (cities ≥15k) | MIT / CC-BY GeoNames | Offline; picks the most populous match and echoes it back |
| Time zones | `zoneinfo` + `tzdata` | — | Historical offsets/DST. Biggest real-world error source |
| Rules | YAML DSL → Python evaluator | — | Ontology/SHACL later |
| Storage | SQLite on a Docker volume | — | |
| LLM | Optional Ollama sidecar (`qwen2.5:3b` default) | — | Only rewords supplied facts; template fallback |
| Bot | python-telegram-bot v21, long polling | LGPL | |

---

## 3. Repository layout (current state)

```
samay/
├─ HANDOFF.md            ← this file
├─ CLAUDE.md             ← instructions for Claude Code
├─ README.md
├─ Dockerfile            ← python:3.12-slim, downloads de440s.bsp at build
├─ docker-compose.yml    ← samay + optional `ollama` (profile: llm)
├─ requirements.txt
├─ .env.example          ← TELEGRAM_TOKEN, OLLAMA_URL, OLLAMA_MODEL
├─ data/                 ← put de440s.bsp here for local runs (git-ignored)
├─ rules/yogas.yaml      ← 8 yogas: Gajakesari, Budhaditya, Chandra-Mangala, 5 Mahapurusha
├─ samay/
│  ├─ ephemeris.py       ← compute_chart(utc, lat, lon) → Chart (sidereal)
│  ├─ vedic.py           ← signs, nakshatra/pada, house_from, navamsa, Vimshottari maha/antar
│  ├─ rules.py           ← YAML DSL: house_from, in_house, in_sign, same_sign, all/any/not
│  ├─ geo.py             ← find_place("Pune, IN"), local_to_utc()
│  ├─ db.py              ← SQLite users table
│  ├─ narrate.py         ← template or Ollama
│  └─ bot.py             ← /start /birth /chart /dasha /today /forget
└─ tests/test_core.py    ← 10 unit tests + 1 ephemeris smoke test (skipped without the .bsp)
```

**Status:** unit tests pass (10 passed, 1 skipped). **The full-chart path hasn't been run yet**
because the build sandbox couldn't download the ephemeris. First thing to do (below).

---

## 4. Next steps (in order)

1. **Get the ephemeris and smoke-test.**
   `curl -o data/de440s.bsp https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp && pytest -q`
   The smoke test checks that the J2000 Sun is ≈256.5° sidereal.
2. **Validate against a reference.** Compare 10–20 charts (various dates/latitudes, including a
   southern-hemisphere one and a DST-boundary one) with Jagannatha Hora or `swetest`. Target:
   planets within 1′, lagna within a few ′, ayanamsa within 1″. Record the results as test
   fixtures. Record the sha256 of `de440s.bsp` and pin it in the Dockerfile with `--checksum`.
3. **Run the bot end to end** locally (`TELEGRAM_TOKEN=… python -m samay.bot`), then
   `docker compose up -d`, then on Oracle Ampere (`docker buildx … --platform linux/arm64`).
4. **Rule provenance pass.** For every rule set `source.locus` to the real chapter/verse and
   `verified: true`. Add `school` and, where useful, `variant_of`.
5. **Grow the rule base:** gochara (transit) rules in `rules/transits.yaml` to interpret `/today`;
   dasha-lord results; more yogas (Raja, Dhana, Viparita Raja, Neecha Bhanga); combustion,
   exaltation/debilitation; navamsa-based rules (needs a `d9_sign` predicate).
6. **Conflict resolution and strength:** decide on a weighting (shadbala or a simpler dignity
   score), and document it in `docs/weighting.md`.
7. **UX:** daily push at the user's chosen local time (PTB `JobQueue`); inline keyboards;
   a disambiguation prompt when a city name is ambiguous or a DST time is ambiguous; i18n
   (Hindi, Marathi).
8. **Privacy:** birth date, time and place are personal data. `/forget` exists. Add a privacy
   note and consider encrypting at rest.
9. **Ontology (later):** export the rule base and chart facts to OWL/SKOS with per-rule
   provenance; evaluate with SHACL rules or a Datalog engine; keep YAML as the authoring format
   if convenient.

## 5. Open decisions
- Ayanamsa: mean Lahiri (current) vs true Chitrapaksha (add nutation)? Offer Raman/KP options?
- Node: mean (current) vs true?
- Dasha year: 365.25 days (current) vs 360 vs sidereal year?
- Kendra reference for Mahapurusha yogas: lagna only (current) or lagna *or* Moon?
- LLM: keep it optional, or ship with a model by default? (Image size and RAM on small VPSes.)
- Licence for samay itself (everything we depend on is permissive, so either way works).

## 6. Optional research phase: testing the rules
Only meaningful if done honestly:
1. Pick a handful of **specific, falsifiable** classical rules *before* touching outcome data.
2. Get birth data with **accurate birth times** and documented life events (biased sources →
   biased results; note the limits).
3. Hold out a test set; don't look at it until the end.
4. **Control:** shuffle birth dates between people, or shift birth years so the season stays the
   same but the planets change. Real charts must beat shuffled ones on the holdout.
5. Control separately for season and birth year (relative-age effect, birth-month confounders).
6. Publish code and results either way. A clean null result is a valid outcome.

## 7. Commands
```bash
pip install -r requirements.txt pytest
curl -o data/de440s.bsp https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp
pytest -q
cp .env.example .env   # add TELEGRAM_TOKEN
SAMAY_EPHEMERIS=data/de440s.bsp python -m samay.bot
docker compose up -d --build                 # bot only
docker compose --profile llm up -d --build   # bot + ollama
docker compose exec ollama ollama pull qwen2.5:3b
```

## 8. Reference libraries (for cross-checking only, not dependencies)
- **PyJHora**: Python port of Jagannatha Hora / P.V.R. Narasimha Rao's *Vedic Astrology – An
  Integrated Approach*. AGPL-3.0. Good for cross-checking results.
- **jyotishganit**: MIT, Skyfield-based. Could be vendored if needed.
- **Jagannatha Hora** (Windows freeware) / **swetest**: reference output for validation.
