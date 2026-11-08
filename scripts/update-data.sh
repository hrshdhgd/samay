#!/usr/bin/env bash
# Refresh the bundled data a reading depends on, then run the tests. Review the diff before
# committing: a changed tzdata can move historical offsets, and with them a chart's lagna.
#
#   scripts/update-data.sh              # tzdata + skyfield in uv.lock
#   scripts/update-data.sh --gazetteer  # also re-download GeoNames and rebuild the place database
set -euo pipefail
cd "$(dirname "$0")/.."

uv lock --upgrade-package tzdata --upgrade-package skyfield
uv sync

if [[ "${1:-}" == "--gazetteer" ]]; then
  rm -rf data/geonames-src
  uv run python scripts/build_gazetteer.py
fi

uv run ruff check
uv run pytest -q
echo "Review: git diff uv.lock data/gazetteer.lock"
