#!/usr/bin/env bash
# Run the whole test suite inside the arm64 image (same architecture as the Oracle Ampere server).
# Needs data/gazetteer.sqlite (scripts/build_gazetteer.py) and a running Docker daemon.
set -euo pipefail
cd "$(dirname "$0")/.."

docker build --platform linux/arm64 --target test -t samay:test .
docker run --rm --platform linux/arm64 samay:test
