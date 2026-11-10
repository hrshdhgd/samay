# syntax=docker/dockerfile:1
# Runs on amd64 and arm64 (Oracle Ampere). Build on the target machine, like stockbro:
#   docker compose build            # runtime image
#   scripts/test-arm64.sh           # test suite inside the arm64 image
FROM python:3.12-slim AS base

# Only the pinned tzdata package is used for time zones, never the image's own copy.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONTZPATH="" \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" \
    SAMAY_DATA_DIR=/app/data SAMAY_RULES_DIR=/app/rules SAMAY_DB=/var/lib/samay/samay.db
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

# Dependencies first so code changes do not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# JPL DE440s (1849-2150). The hash is the same one scripts/fetch-ephemeris.sh checks.
# Create /app/data first: ADD would otherwise create it with the file's mode (644), which the
# non-root runtime user cannot enter.
RUN mkdir -p /app/data && chmod 755 /app/data
ADD --checksum=sha256:c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2 --chmod=644 \
    https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp /app/data/de440s.bsp

COPY samay ./samay
COPY rules ./rules
COPY data/profiles ./data/profiles
COPY data/time_standards ./data/time_standards
COPY data/entries ./data/entries
COPY data/rules ./data/rules
# Built once by scripts/build_gazetteer.py; nothing is downloaded or built on the server.
COPY data/gazetteer.sqlite data/gazetteer.lock ./data/
COPY scripts/build_gazetteer.py ./scripts/build_gazetteer.py
RUN uv sync --frozen --no-dev \
    && python scripts/build_gazetteer.py --verify \
    && chmod -R a+rX /app/data /app/rules /app/samay /app/scripts

ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA


# Test stage: the suite runs against the real database and ephemeris on the target architecture.
FROM base AS test
RUN uv sync --frozen
COPY tests ./tests
CMD ["pytest", "-q"]


# Runtime stage (the default target, so it must stay last).
FROM base AS runtime
RUN useradd --create-home --uid 10001 samay \
    && mkdir -p /var/lib/samay && chown samay /var/lib/samay
USER samay
VOLUME ["/var/lib/samay"]
CMD ["python", "-m", "samay.bot"]
