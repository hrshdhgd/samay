"""The engine against dates read from the family's own printed calendar."""

from datetime import date
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


@pytest.mark.parametrize("row", DATA["sankashti"], ids=lambda r: r["date"].isoformat())
def test_the_family_sankashti_is_the_engines_primary_day(row):
    """Krishna Chaturthi at moonrise (20:59 at Mangaluru on 27 Nov 2026), with the shipped rule."""
    from samay.engine import observances as ob
    from samay.engine.panchang_profile import load_panchang_profile

    profile = load_panchang_profile()
    found = ob.observances_for(
        profile.observances["sankashti"].rules,
        profile.sampradaya,
        SITE,
        row["date"],
        row["date"],
        profile.ayanamsa,
        profile.margin_minutes,
        profile.sunrise_definition,
    )
    assert [o.primary for o in found] == [row["date"]]


@pytest.mark.parametrize("name", ["purnima", "amavasya"])
def test_family_purnima_and_amavasya_are_the_engines_primary_days(name):
    from samay.engine import observances as ob
    from samay.engine.panchang_profile import load_panchang_profile

    profile = load_panchang_profile()
    for row in DATA[name]:
        found = ob.observances_for(
            profile.observances[name].rules,
            profile.sampradaya,
            SITE,
            row["date"],
            row["date"],
            profile.ayanamsa,
            profile.margin_minutes,
            profile.sunrise_definition,
        )
        assert [o.primary for o in found] == [row["date"]], row


@pytest.mark.parametrize("day", [date(2026, 11, 25), date(2026, 12, 23)])
def test_rohini_days_the_family_marks_carry_the_rohini_note(day):
    from samay import service
    from samay.engine.geo import Place

    place = Place("mangaluru", "Mangaluru", "IN", "Karnataka", None, 12.9141, 74.856, "Asia/Kolkata", 488000)
    notes = service.panchang_report(place, day).care_notes
    assert len(notes) == 1 and "Rohini" in notes[0] and "favourable" in notes[0]


def test_no_other_day_in_november_and_december_is_a_rohini_day():
    from datetime import timedelta

    d, found = date(2026, 11, 1), []
    while d <= date(2026, 12, 31):
        if panchang.day_facts(SITE, d).nakshatra.name == "Rohini":
            found.append(d)
        d += timedelta(days=1)
    assert found == [date(2026, 11, 25), date(2026, 12, 23)]
