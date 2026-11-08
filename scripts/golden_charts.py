"""Generate golden-chart reference values with Swiss Ephemeris (reference oracle only).

Run: uv run --with pyswisseph python scripts/golden_charts.py
pyswisseph is AGPL and is never a samay dependency; only its output values are committed.
Settings match the parashari-lahiri profile: Lahiri ayanamsa (mean), mean node, Moshier
ephemeris (built in, no data files).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import swisseph as swe

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_charts.json"

CHARTS = [
    ("pune-1990", datetime(1990, 8, 15, 9, 0), 18.5196, 73.8553),
    ("pune-j2000", datetime(2000, 1, 1, 12, 0), 18.5196, 73.8553),
    ("sydney-1985-southern", datetime(1985, 3, 20, 22, 15), -33.8688, 151.2093),
    ("new-york-2021-dst-boundary", datetime(2021, 11, 7, 5, 30), 40.7128, -74.0060),
    ("pune-1952-pre-ist", datetime(1952, 8, 5, 0, 30), 18.5196, 73.8553),
]
BODIES = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY, "venus": swe.VENUS,
    "mars": swe.MARS, "jupiter": swe.JUPITER, "saturn": swe.SATURN, "rahu": swe.MEAN_NODE,
}


def main() -> None:
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_MOSEPH | swe.FLG_SIDEREAL
    out = {"generator": f"pyswisseph {swe.version}, Moshier, SIDM_LAHIRI, mean node", "charts": []}
    for name, utc, lat, lon in CHARTS:
        jd = swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60)
        planets = {k: swe.calc_ut(jd, body, flags)[0][0] for k, body in BODIES.items()}
        planets["ketu"] = (planets["rahu"] + 180.0) % 360.0
        _, ascmc = swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)
        out["charts"].append({
            "name": name,
            "utc": utc.replace(tzinfo=timezone.utc).isoformat(),
            "latitude": lat,
            "longitude": lon,
            "ayanamsa_mean": swe.get_ayanamsa_ex_ut(jd, swe.FLG_MOSEPH | swe.FLG_NONUT)[1],
            "ascendant": ascmc[0],
            "planets": planets,
        })
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
