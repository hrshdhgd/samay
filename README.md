# samay

A self-contained Telegram bot for Jyotish (Vedic astrology): sidereal charts computed offline
from NASA JPL ephemerides and interpreted by a rule engine built from classical texts, with
each rule citing its source.

> Traditional interpretation, for reflection and fun. Not a guarantee of events.

## Quick start
```bash
cp .env.example .env            # set TELEGRAM_TOKEN from @BotFather
docker compose up -d --build    # add --profile llm for local Ollama narration
```

## Bot commands
`/birth DD-MM-YYYY HH:MM City[, CC]` · `/chart` · `/dasha` · `/today` · `/forget`

## Development
```bash
pip install -r requirements.txt pytest
curl -o data/de440s.bsp https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp
pytest -q
```

See `HANDOFF.md` for design decisions and the roadmap.
