# samay

A self-contained Telegram bot for Jyotish (Vedic astrology): sidereal charts computed offline
from NASA JPL ephemerides and interpreted by a rule engine built from classical texts, with
each rule citing its source.

> Traditional interpretation, for reflection and fun. Not a guarantee of events.

## Development
```bash
uv sync
scripts/fetch-ephemeris.sh      # downloads and checksum-verifies data/de440s.bsp
uv run pytest -q
uv run ruff check
```

## CLI
```bash
uv run samay chart --date 1990-08-15 --time 14:30 --place "Pune"
uv run samay dasha ... --now 2026-01-01T00:00:00
uv run samay today ...
uv run samay data-info          # versions of every data source a reading uses
```
Enter the local clock time at the birthplace; samay works out the offset. If a place or a
time is ambiguous, the command exits with code 2 and lists `--choice` or `--fold` options.

Every chart shows the time standard used and its confidence, the tradition profile, and a
version stamp. Charts say "not yet checked against reference software" until validation
(sub-project 2) is complete.

## Data
- Ephemeris: JPL DE440s (1849–2150), public domain.
- Places: GeoNames (CC-BY 4.0): cities500 worldwide plus full India, US, Ukraine and Italy files,
  built into `data/gazetteer.sqlite` by `scripts/build_gazetteer.py` and pinned in `data/gazetteer.lock`.
- Time zones: IANA tzdata, overridden by cited entries in `data/time_standards/`.
- Golden charts in `tests/fixtures/` were generated with Swiss Ephemeris
  (`scripts/golden_charts.py`), used as a reference oracle only.

## Telegram bot
```bash
echo "ALLOWED_CHAT_IDS=<your chat id>" > .env     # git-ignored; comma-separate several ids
export SAMAY_TELEGRAM_BOT_TOKEN=<token from @BotFather>   # or TELEGRAM_TOKEN
uv run samay bot
```
Long polling, so no public port. Only chats listed in `ALLOWED_CHAT_IDS` get answers (the bot
refuses to start with an empty list). Relatives use a button menu and a guided conversation; the
slash commands `/birth /chart /dasha /today /forget` also work. Birth details are stored in
plaintext in the SQLite file until the encryption sub-project, so do not deploy before that.

### Questions
Relatives can type a question or tap **❓ Ask a question**. Answers are built only from checked
entries in `data/entries/` (quoted word for word, with their citation) plus facts from the person's
own chart. The local model, when `OLLAMA_URL` is set, only sorts a question into a known topic; it
never writes the answer. Questions without a sourced answer say so, and only their topic key (never
the words) is counted for `uv run samay research-queue`. How entries are researched and checked:
`research/program.md`.

See `docs/superpowers/specs/2026-11-08-foundation-design.md` for the design and roadmap.
