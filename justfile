# samay: every common command in one place.   just --list   shows them all.
# Needs: uv, just. Docker for the image tasks; ssh access to the server for deploys.

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

# The Telegram bot and most settings come from .env (see .env.example) and the environment.

default:
    @just --list --unsorted

# ---------------------------------------------------------------------------------- set up

# Install dependencies, fetch the ephemeris (checksum-verified) and build the place database if missing.
setup:
    uv sync
    scripts/fetch-ephemeris.sh
    test -f data/gazetteer.sqlite || uv run python scripts/build_gazetteer.py
    @echo "ready. Next: just test"

# ---------------------------------------------------------------------------------- everyday

# Run the Telegram bot (needs TELEGRAM_TOKEN or SAMAY_TELEGRAM_BOT_TOKEN, and ALLOWED_CHAT_IDS in .env).
bot:
    uv run samay bot

# Run the tests (all of them; the ones needing the full place database skip if it is not built).
test *args:
    uv run pytest -q {{args}}

# Lint.
lint:
    uv run ruff check

# Lint, then test: what CI runs.
check: lint test

# ---------------------------------------------------------------------------------- try it out

# Print a birth chart, e.g.:  just chart 1990-08-15 14:30 Pune
chart date time place:
    uv run samay chart --date {{date}} --time {{time}} --place "{{place}}"

# Save the chart picture too, e.g.:  just picture 1990-08-15 14:30 Pune south out.png   (style: south or north)
picture date time place style="south" out="chart.png":
    uv run samay chart --date {{date}} --time {{time}} --place "{{place}}" --style {{style}} --image {{out}} > /dev/null
    @echo "saved {{out}}"

# Dasha periods, e.g.:  just dasha 1990-08-15 14:30 Pune
dasha date time place:
    uv run samay dasha --date {{date}} --time {{time}} --place "{{place}}"

# Today's transits, e.g.:  just today 1990-08-15 14:30 Pune
today date time place:
    uv run samay today --date {{date}} --time {{time}} --place "{{place}}"

# Versions of every data source a reading depends on.
data-info:
    uv run samay data-info

# ---------------------------------------------------------------------------------- research

# Topics people asked about that have no sourced answer yet, most wanted first.
research-queue:
    uv run samay research-queue

# How many sourced entries exist, and how many a person has checked.
entries:
    uv run python -c "from samay.engine.entries import load_entries; e = load_entries(); print(len(e), 'entries;', sum(x.servable for x in e), 'checked and shown;', sum(not x.servable for x in e), 'unchecked')"

# ---------------------------------------------------------------------------------- data and keys

# Rebuild the place database from GeoNames (downloads on first run; the result is pinned in data/gazetteer.lock).
gazetteer:
    uv run python scripts/build_gazetteer.py

# Check the place database against its lock.
verify-gazetteer:
    uv run python scripts/build_gazetteer.py --verify

# Update tzdata and skyfield, then test. Add "--gazetteer" to re-download the place data too.
update-data *args:
    scripts/update-data.sh {{args}}

# Regenerate the Swiss Ephemeris reference values the golden tests compare against.
golden:
    uv run --with pyswisseph python scripts/golden_charts.py
    uv run --with pyswisseph python scripts/golden_suntimes.py

# Make a new database encryption key (put it in .env as SAMAY_DB_KEY and keep a copy somewhere safe).
keygen:
    uv run samay keygen

# Copy the database (personal data stays encrypted; the key is NOT included): just backup backups/samay-1.db
backup out:
    mkdir -p "$(dirname {{out}})"
    uv run samay backup --out {{out}}

# ---------------------------------------------------------------------------------- Docker and deploy

# Build the server image locally (arm64, same as the Oracle server).
docker-build:
    docker build --platform linux/arm64 --target runtime -t samay:runtime --build-arg GIT_SHA=$(git rev-parse --short HEAD) .

# Run the whole test suite inside the arm64 image.
docker-test:
    scripts/test-arm64.sh

# Show the deploy plan and run the local checks. Nothing remote happens.
deploy-plan:
    scripts/deploy-oracle.sh

# First deploy only: create the server's .env (needs SAMAY_TELEGRAM_BOT_TOKEN in your shell). Stop the local bot first.
deploy-init:
    scripts/deploy-oracle.sh --init-env

# Deploy to the Oracle server (stop the local bot first: two copies fight over Telegram's updates).
deploy:
    scripts/deploy-oracle.sh --go

# Follow the bot's log on the server.
server-logs:
    ssh ${SAMAY_DEPLOY_HOST:-stockbro} docker logs -f --tail 50 samay-bot

# Is the bot running on the server?
server-status:
    ssh ${SAMAY_DEPLOY_HOST:-stockbro} "docker ps --filter name=samay-bot --format '{{{{.Names}}  {{{{.Status}}'"

# Restart the bot on the server.
server-restart:
    ssh ${SAMAY_DEPLOY_HOST:-stockbro} docker restart samay-bot
