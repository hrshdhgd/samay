# samay — notes for Claude Code

Read `HANDOFF.md` first. It has the full background, decisions, and the ordered next steps (§4).

## Non-negotiables
- **Self-contained.** No runtime calls to third-party compute or APIs except Telegram (and the
  optional local Ollama sidecar). Data files (ephemeris, gazetteer, tzdata) are bundled.
- **Permissive dependencies only** (MIT/BSD/Apache/LGPL). No AGPL (PyJHora, Swiss Ephemeris
  without a licence) and no cloud-backed libs (VedAstro).
- **Honest framing.** Readings stay labelled as traditional interpretation, not a guarantee; keep the
  disclaimer. Owner's decision (2026-11-24): for a coming day, week, month or year the LLM may give an
  informed, forward-looking reading (`qa.AI_FORECAST_SYSTEM`, labelled as an AI reading), but only from
  facts computed by the engine and checked rules, never inventing positions, dates or claims. Elsewhere
  it only rewords the sourced answer.
- **Provenance.** Every rule in `rules/*.yaml` has `source.text`, `source.locus` and
  `source.verified`. Effects are paraphrased, never copied from copyrighted translations.
- **Portable.** Must build and run on both amd64 and arm64 (Oracle Ampere).

## Conventions
- Python 3.12, type hints, frozen dataclasses. `samay/engine/` is pure and imports nothing else
  from samay; front ends call only `samay/service.py`; all user-facing wording is in `render/`.
- All longitudes are sidereal degrees in [0, 360). Times are timezone-aware UTC internally.
- Disputed calculation choices belong in `data/profiles/*.yaml`, not in code.
- Historical offsets go in `data/time_standards/*.yaml` only with a cited primary source.
- New rule predicates go in `rules.evaluate` with a test in `tests/`.
- Run `uv run ruff check` and `uv run pytest -q` before committing
  (`scripts/fetch-ephemeris.sh` first).

## Start here
Spec: `docs/superpowers/specs/2026-11-08-foundation-design.md`. Plans: `docs/superpowers/plans/`.
