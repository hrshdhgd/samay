"""Generate sunrise/sunset reference values with Swiss Ephemeris (reference oracle only).

Run: uv run --with pyswisseph python scripts/golden_suntimes.py
pyswisseph is AGPL and is never a samay dependency; only its output values are committed.
Conventions: upper limb of the Sun, standard refraction (1013.25 hPa, 15 C), Moshier ephemeris.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_suntimes.json"
CASES = [
    ("pune", 18.5196, 73.8553, "Asia/Kolkata", date(2026, 11, 9)),
    ("new-delhi", 28.6139, 77.2090, "Asia/Kolkata", date(2026, 11, 9)),
    ("maplewood-mn-dst-ended", 44.9530, -93.0230, "America/Chicago", date(2026, 11, 9)),
    ("kyiv-midsummer", 50.4501, 30.5234, "Europe/Kyiv", date(2026, 6, 21)),
    ("sydney-southern", -33.8688, 151.2093, "Australia/Sydney", date(2026, 12, 21)),
    ("mumbai-1990", 19.0760, 72.8777, "Asia/Kolkata", date(1990, 8, 15)),
]


def event(lat: float, lon: float, zone: ZoneInfo, day: date, kind: int) -> str | None:
    start = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(UTC)
    jd = swe.julday(start.year, start.month, start.day, start.hour + start.minute / 60)
    res, t = swe.rise_trans(jd, swe.SUN, kind, (lon, lat, 0), 1013.25, 15.0, swe.FLG_MOSEPH)
    if res != 0:
        return None
    y, mo, d, h = swe.revjul(t[0])
    return (datetime(y, mo, d, tzinfo=UTC) + timedelta(hours=h)).astimezone(zone).isoformat()


def main() -> None:
    out = {"generator": f"pyswisseph {swe.version}, Moshier, upper limb, standard refraction", "cases": []}
    for name, lat, lon, tz, day in CASES:
        zone = ZoneInfo(tz)
        out["cases"].append({
            "name": name, "latitude": lat, "longitude": lon, "tz": tz, "date": day.isoformat(),
            "sunrise": event(lat, lon, zone, day, swe.CALC_RISE),
            "sunset": event(lat, lon, zone, day, swe.CALC_SET),
        })
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
