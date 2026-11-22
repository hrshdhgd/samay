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
def test_sankashti_day_is_krishna_tritiya_at_sunrise_with_chaturthi_arriving_before_moonrise(row):
    from datetime import timedelta

    facts = panchang.day_facts(SITE, row["date"])
    assert facts.tithi.name == "Krishna Tritiya"  # Chaturthi begins later that morning
    assert facts.tithi.end.astimezone(facts.sunrise.tzinfo) < facts.sunset + timedelta(hours=3)
