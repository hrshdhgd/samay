# samay — notes for Claude Code

Read `HANDOFF.md` first. It has the full background, decisions, and the ordered next steps (§4).

## Non-negotiables
- **Self-contained.** No runtime calls to third-party compute or APIs except Telegram (and the
  optional local Ollama sidecar). Data files (ephemeris, gazetteer, tzdata) are bundled.
- **Permissive dependencies only** (MIT/BSD/Apache/LGPL). No AGPL (PyJHora, Swiss Ephemeris
  without a licence) and no cloud-backed libs (VedAstro).
- **Honest framing.** Readings are traditional interpretation, not accurate prediction. Keep the
  disclaimer. The LLM may only reword facts computed by the engine.
- **Provenance.** Every rule in `rules/*.yaml` has `source.text`, `source.locus` and
  `source.verified`. Effects are paraphrased, never copied from copyrighted translations.
- **Portable.** Must build and run on both amd64 and arm64 (Oracle Ampere).

## Conventions
- Python 3.12, type hints, frozen dataclasses, pure functions in `vedic.py`/`rules.py`.
- All longitudes are sidereal degrees in [0, 360). Times are timezone-aware UTC internally.
- New rule predicates go in `rules.evaluate` with a test in `tests/`.
- Run `pytest -q` before committing. The ephemeris smoke test needs `data/de440s.bsp`.

## Start here
`HANDOFF.md` §4 step 1: download the ephemeris, run the tests, then validate charts against
Jagannatha Hora / swetest and turn those comparisons into fixtures.
