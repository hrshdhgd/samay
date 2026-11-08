"""samay vs Swiss Ephemeris on fixed charts. Tolerances come from the spec; a failure is a
finding to investigate, not a tolerance to loosen."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from samay.engine.ephemeris import compute_chart
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden_charts.json").read_text())["charts"]
PLANET_TOL = 1 / 60  # 1 arcminute
LAGNA_TOL = 3 / 60  # 3 arcminutes
AYANAMSA_TOL = 1 / 3600  # 1 arcsecond


def _diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


@pytest.fixture(params=GOLDEN, ids=[g["name"] for g in GOLDEN])
def case(request):
    g = request.param
    return g, compute_chart(datetime.fromisoformat(g["utc"]), g["latitude"], g["longitude"])


def test_planets(case):
    g, chart = case
    errors = {p: _diff(chart.planets[p].longitude, ref) * 60 for p, ref in g["planets"].items()}
    assert max(errors.values()) < PLANET_TOL * 60, f"arcmin errors: {errors}"


def test_lagna(case):
    g, chart = case
    assert _diff(chart.ascendant, g["ascendant"]) < LAGNA_TOL


def test_ayanamsa(case):
    g, chart = case
    assert _diff(chart.ayanamsa, g["ayanamsa_mean"]) < AYANAMSA_TOL
