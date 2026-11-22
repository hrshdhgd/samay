"""Regenerate tests/fixtures/golden_panchang.json from Swiss Ephemeris (Moshier theory, no data files).

Dev tool only: `uv run --with pyswisseph python scripts/golden_panchang.py`.
pyswisseph is AGPL, so it is never a runtime dependency; only the JSON it writes is kept.
Independent of samay's own search code on purpose.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import swisseph as swe

swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
FLAGS = swe.FLG_SIDEREAL | swe.FLG_MOSEPH
OUT = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_panchang.json"
)

CASES = [
    "1985-03-07T01:00",
    "1999-12-31T06:00",
    "2000-01-01T00:00",
    "2010-06-21T05:30",
    "2015-09-28T02:15",
    "2019-02-04T23:50",
    "2022-10-25T13:00",
    "2023-07-04T00:10",
    "2024-04-08T18:00",
    "2025-11-05T02:00",
    "2026-03-14T01:00",
    "2026-04-14T00:43",
    "2026-11-20T01:13",
    "2026-11-21T01:14",
    "2027-01-15T06:30",
    "2030-08-01T03:00",
    "2040-12-25T11:11",
]


def lon(body: int, t: datetime) -> float:
    jd = swe.julday(
        t.year,
        t.month,
        t.day,
        t.hour + t.minute / 60 + t.second / 3600 + t.microsecond / 3.6e9,
    )
    return swe.calc_ut(jd, body, FLAGS)[0][0] % 360.0


QUANT = {
    "tithi": (lambda t: (lon(swe.MOON, t) - lon(swe.SUN, t)) % 360.0, 12.0),
    "karana": (lambda t: (lon(swe.MOON, t) - lon(swe.SUN, t)) % 360.0, 6.0),
    "nakshatra": (lambda t: lon(swe.MOON, t), 360.0 / 27.0),
    "yoga": (lambda t: (lon(swe.SUN, t) + lon(swe.MOON, t)) % 360.0, 360.0 / 27.0),
}


def cell(kind: str, t: datetime) -> int:
    angle, width = QUANT[kind]
    return int(angle(t) // width)


def edge(kind: str, t: datetime, forward: bool) -> datetime:
    """Boundary of the element holding t: hourly scan, then bisection to half a second."""
    base = cell(kind, t)
    step = timedelta(hours=1) * (1 if forward else -1)
    inside, outside = t, t + step
    while cell(kind, outside) == base:
        inside, outside = outside, outside + step
    while abs(outside - inside) > timedelta(milliseconds=500):
        mid = inside + (outside - inside) / 2
        if cell(kind, mid) == base:
            inside = mid
        else:
            outside = mid
    return outside if forward else inside


def main() -> None:
    cases = []
    for text in CASES:
        t = datetime.fromisoformat(text).replace(tzinfo=UTC)
        entry: dict = {"instant": t.isoformat()}
        for kind in QUANT:
            entry[kind] = {
                "number": cell(kind, t) + 1,
                "start": edge(kind, t, False).isoformat(),
                "end": edge(kind, t, True).isoformat(),
            }
        cases.append(entry)
    OUT.write_text(
        json.dumps(
            {
                "source": "Swiss Ephemeris (Moshier), Lahiri sidereal, geocentric",
                "cases": cases,
            },
            indent=1,
        )
    )
    print(f"wrote {OUT} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
