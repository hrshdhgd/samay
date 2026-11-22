"""The engine's observance days against an independent published computation, each source tagged with its tradition.
Every difference must be listed in the fixture's known_divergences with a cause; N and the rules are never tuned to pass."""
from datetime import date
from pathlib import Path

import pytest
import yaml

from samay.engine import observances as ob
from samay.engine.panchang import Site
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
FIXTURES = Path(__file__).parent / "fixtures"
# The provisional Smarta rules (the shipped profile marks them unverified); the Pradosha window is a placeholder.
RULES = {
    "ekadashi": ob.Rule(tithis=(11, 26)),
    "pradosha": ob.Rule(tithis=(13, 28), anchor="sunset", start_minutes=0, end_minutes=72),
    "purnima": ob.Rule(tithis=(15,)),
    "amavasya": ob.Rule(tithis=(30,)),
}


def test_engine_agrees_with_the_tulu_panchanga_app_or_every_difference_is_explained():
    data = yaml.safe_load((FIXTURES / "tulu_app_observances.yaml").read_text())
    p = data["place"]
    site = Site(p["latitude"], p["longitude"], p["tz"])
    theirs = {(d["observance"], d["date"]) for d in data["dates"]}
    explained = {(d["observance"], d["date"]) for d in data["known_divergences"]}
    problems = []
    for year in sorted({d.year for _, d in theirs}):
        for name, rule in RULES.items():
            found = ob.observances_between(rule, site, date(year, 1, 1), date(year, 12, 31), margin_minutes=6)
            ours = {(name, o.primary) for o in found if o.primary and o.primary.year == year}
            listed = {(n, d) for n, d in theirs if n == name and d.year == year}
            problems += [(n, d.isoformat()) for n, d in sorted(ours ^ listed) if (n, d) not in explained]
    assert not problems, f"unexplained differences (observance, date): {problems}"
