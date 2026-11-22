"""The engine against dates read from the family's own printed calendar."""

from pathlib import Path

import pytest
import yaml

from samay.engine import panchang
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
DATA = yaml.safe_load((Path(__file__).parent / "fixtures" / "family_calendar_2026.yaml").read_text())
P = DATA["place"]
SITE = panchang.Site(P["latitude"], P["longitude"], P["tz"])


@pytest.mark.parametrize("row", DATA["nakshatra_days"], ids=lambda r: r["family_name"])
def test_the_moon_is_in_the_nakshatra_the_family_calendar_marks(row):
    assert panchang.day_facts(SITE, row["date"]).nakshatra.name == row["nakshatra"]


@pytest.mark.parametrize("row", DATA["sankashti"], ids=lambda r: r["date"].isoformat())
def test_sankashti_day_is_krishna_tritiya_at_sunrise_with_chaturthi_arriving_before_moonrise(
    row,
):
    from datetime import timedelta

    facts = panchang.day_facts(SITE, row["date"])
    assert facts.tithi.name == "Krishna Tritiya"  # Chaturthi begins later that morning
    assert facts.tithi.end.astimezone(facts.sunrise.tzinfo) < facts.sunset + timedelta(hours=3)


@pytest.mark.parametrize("row", DATA["ekadashi"], ids=lambda r: r["date"].isoformat())
def test_the_family_ekadashi_is_the_engines_primary_day(row):
    """With the shipped profile (disc-centre sunrise, chosen because of this very date) the primary day is the family's.
    At Mangaluru on 20 Nov 2026 the Ekadashi tithi ends 06:32:01 and the Sun's centre rises at 06:32:52.
    """
    from samay.engine import observances as ob
    from samay.engine.panchang_profile import load_panchang_profile

    profile = load_panchang_profile()
    found = ob.observances_for(
        profile.observances["ekadashi"].rules,
        profile.sampradaya,
        SITE,
        row["date"],
        row["date"],
        profile.ayanamsa,
        profile.margin_minutes,
        profile.sunrise_definition,
    )
    assert [o.primary for o in found] == [row["date"]]
