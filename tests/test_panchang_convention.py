"""The engine's observance days against an independent published computation, each source tagged with its tradition.
Every difference must be listed in the fixture's known_divergences with a cause, and every listed one must still occur (a stale entry fails). The rules are the shipped ones, never tuned."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from samay.engine import observances as ob
from samay.engine.panchang import Site
from samay.engine.panchang_profile import load_panchang_profile
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
FIXTURES = Path(__file__).parent / "fixtures"


# The rules come from the shipped profile, so this test cannot drift from what the bot uses: the Smarta rule where an
# observance has one, otherwise its tradition-independent "all" rule.
def _shipped_rules() -> dict[str, ob.Rule]:
    rules = {
        name: spec.rules.get("smarta", spec.rules.get("all"))
        for name, spec in load_panchang_profile().observances.items()
    }
    assert all(rules.values())
    return rules


RULES = _shipped_rules()


def test_engine_agrees_with_the_tulu_panchanga_app_or_every_difference_is_explained():
    data = yaml.safe_load((FIXTURES / "tulu_app_observances.yaml").read_text())
    p = data["place"]
    site = Site(p["latitude"], p["longitude"], p["tz"])
    theirs = {(d["observance"], d["date"]) for d in data["dates"]}
    explained = {(d["observance"], d["date"]) for d in data["known_divergences"]}
    problems, occurred = [], set()
    for year in sorted({d.year for _, d in theirs}):
        for name, rule in RULES.items():
            profile = load_panchang_profile()
            found = ob.observances_between(
                rule,
                site,
                date(year, 1, 1),
                date(year, 12, 31),
                profile.ayanamsa,
                profile.margin_minutes,
                profile.sunrise_definition,
            )
            ours = {(name, o.primary) for o in found if o.primary and o.primary.year == year}
            listed = {(n, d) for n, d in theirs if n == name and d.year == year}
            differing = ours ^ listed
            occurred |= differing & explained
            problems += [(n, d.isoformat()) for n, d in sorted(differing) if (n, d) not in explained]
    assert not problems, f"unexplained differences (observance, date): {problems}"
    stale = sorted((n, d.isoformat()) for n, d in explained - occurred)
    assert not stale, f"known_divergences that no longer occur (remove them): {stale}"
