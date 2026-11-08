#!/usr/bin/env bash
# Download JPL DE440s (1849-2150) and verify it. The Dockerfile pins the same hash.
set -euo pipefail

URL="https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp"
SHA256="c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"
DEST="${1:-data/de440s.bsp}"

if [[ ! -f "$DEST" ]]; then
  mkdir -p "$(dirname "$DEST")"
  curl -sSfL -o "$DEST.part" "$URL"
  mv "$DEST.part" "$DEST"
fi

actual="$(shasum -a 256 "$DEST" | cut -d' ' -f1)"
if [[ "$actual" != "$SHA256" ]]; then
  echo "checksum mismatch for $DEST: got $actual, expected $SHA256" >&2
  exit 1
fi
echo "ok: $DEST"
