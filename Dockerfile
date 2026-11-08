# syntax=docker/dockerfile:1
# Multi-arch friendly (amd64 / arm64 e.g. Oracle Ampere):
#   docker buildx build --platform linux/amd64,linux/arm64 -t samay:latest .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SAMAY_EPHEMERIS=/app/data/de440s.bsp SAMAY_DB=/var/lib/samay/samay.db
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# JPL DE440s (1849-2150, ~32 MB). Baked into the image so runtime is fully offline.
# TODO: pin with --checksum=sha256:<hash> once recorded.
ADD --chmod=644 https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp /app/data/de440s.bsp

COPY samay ./samay
COPY rules ./rules

RUN useradd --create-home --uid 10001 samay && mkdir -p /var/lib/samay && chown samay /var/lib/samay
USER samay
VOLUME ["/var/lib/samay"]
CMD ["python", "-m", "samay.bot"]
