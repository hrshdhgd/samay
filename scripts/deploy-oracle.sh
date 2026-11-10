#!/usr/bin/env bash
# Deploy samay to the Oracle server, the same way stockbro is deployed: rsync the repo, build the
# image on the server (arm64, native), start it with docker compose.
#
#   scripts/deploy-oracle.sh            show the plan and run the local checks; nothing remote happens
#   scripts/deploy-oracle.sh --init-env first time only: create the server's .env (never overwrites one)
#   scripts/deploy-oracle.sh --go       deploy
#
# Settings (environment): SAMAY_DEPLOY_HOST (ssh alias, default "stockbro"), SAMAY_DEPLOY_DIR
# (default "~/samay"), SAMAY_TELEGRAM_BOT_TOKEN (only for --init-env), SAMAY_ALLOW_DIRTY=1.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${SAMAY_DEPLOY_HOST:-stockbro}"
DIR="${SAMAY_DEPLOY_DIR:-~/samay}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.oracle.yml"
REQUIRED_ENV=(TELEGRAM_TOKEN ALLOWED_CHAT_IDS SAMAY_DB_KEY)
SERVER_KEY_COPY="data/samay.server.key"   # local copy of the server's database key; git-ignored
MODE=plan INIT=0
for arg in "$@"; do
  case "$arg" in
    --go) MODE=go ;;
    --init-env) INIT=1; MODE=go ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
die() { printf 'STOP: %s\n' "$*" >&2; exit 1; }

# ---- local checks (nothing leaves this machine) ---------------------------------------------------
say "== local checks"
[[ -z "$(git status --porcelain --untracked-files=no)" || "${SAMAY_ALLOW_DIRTY:-}" == 1 ]] \
  || die "uncommitted changes: commit them first so the server runs a known commit (or SAMAY_ALLOW_DIRTY=1)"
SHA="$(git rev-parse --short HEAD)"
say "commit to deploy: $SHA"
uv run python scripts/build_gazetteer.py --verify >/dev/null || die "data/gazetteer.sqlite does not match data/gazetteer.lock"
say "place database matches its lock"
[[ -f data/de440s.bsp ]] && scripts/fetch-ephemeris.sh >/dev/null && say "ephemeris checksum ok"
uv run ruff check >/dev/null || die "lint fails"
uv run pytest -q 2>&1 | tail -1
grep -q '^ALLOWED_CHAT_IDS=.\+' .env 2>/dev/null || die "local .env needs ALLOWED_CHAT_IDS"
$COMPOSE config -q >/dev/null 2>&1 || die "docker compose config is invalid"
say "compose files are valid"

say
say "== plan (host: $HOST, directory: $DIR)"
say "1. ssh $HOST: check the connection, make $DIR"
say "2. rsync the repo to $HOST:$DIR (not .git, .env, local database or key, source dumps, research sources)"
say "3. check the server's .env has: ${REQUIRED_ENV[*]}  (values are never printed)"
say "4. on the server: GIT_SHA=$SHA $COMPOSE up -d --build"
say "5. show the start-up log line"
if [[ "$MODE" == plan ]]; then
  say; say "Nothing was changed. Run again with --go to deploy (first time: --init-env)."
  exit 0
fi

# ---- remote steps -----------------------------------------------------------------------------------
say; say "== deploying"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" true || die "cannot ssh to $HOST"
ssh "$HOST" "mkdir -p $DIR"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '.env' --exclude '*.key' --exclude '*.db' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude '.DS_Store' \
  --exclude 'data/geonames-src' --exclude 'data/de440s.bsp' --exclude 'research/sources' \
  ./ "$HOST:$DIR/"
say "files transferred"

if (( INIT )); then
  ssh "$HOST" "test ! -e $DIR/.env" || die "$DIR/.env already exists on the server; not overwriting it"
  [[ -n "${SAMAY_TELEGRAM_BOT_TOKEN:-}" ]] || die "set SAMAY_TELEGRAM_BOT_TOKEN to create the server .env"
  if [[ ! -f "$SERVER_KEY_COPY" ]]; then
    ( umask 077; uv run samay keygen > "$SERVER_KEY_COPY" )
    say "made a database key and saved a copy at $SERVER_KEY_COPY"
    say ">>> BACK THAT FILE UP somewhere safe now. Without it the server's data cannot be read. <<<"
  fi
  # The secrets go over stdin, so they never appear in a process list or the shell history.
  {
    printf 'TELEGRAM_TOKEN=%s\n' "$SAMAY_TELEGRAM_BOT_TOKEN"
    grep '^ALLOWED_CHAT_IDS=' .env
    printf 'SAMAY_DB_KEY=%s\n' "$(cat "$SERVER_KEY_COPY")"
    printf 'OLLAMA_URL=%s\n' "http://172.17.0.1:11434"   # the host's Ollama, as stockbro uses it
  } | ssh "$HOST" "umask 077; cat > $DIR/.env"
  say "created $DIR/.env on the server (mode 600)"
fi

for var in "${REQUIRED_ENV[@]}"; do
  ssh "$HOST" "grep -q '^$var=.\+' $DIR/.env" || die "$DIR/.env on the server lacks $var (use --init-env the first time)"
done
say "server .env has all required settings"

ssh "$HOST" "cd $DIR && GIT_SHA=$SHA $COMPOSE up -d --build"
sleep 8
ssh "$HOST" "docker logs --tail 15 samay-bot 2>&1 | grep -E 'samay (starting|ready)|rror' || true"
say "done. Follow the log with: ssh $HOST docker logs -f samay-bot"
