import os
from datetime import datetime, timezone

import pytest

from samay.ephemeris import Chart, Placement, ascendant_tropical, lahiri_ayanamsa, mean_lunar_node
from samay.geo import find_place, local_to_utc
from samay.rules import Context, evaluate, fired, load_rules
from samay.vedic import (
    DASHA_ORDER, antardashas, current_dasha, house_from, nakshatra, navamsa_sign, vimshottari,
)

BIRTH = datetime(1990, 8, 15, 9, 0, tzinfo=timezone.utc)


def test_lahiri_at_j2000():
    assert lahiri_ayanamsa(2451545.0) == pytest.approx(23.857, abs=0.002)


def test_mean_node_at_j2000():
    assert mean_lunar_node(2451545.0) == pytest.approx(125.0445, abs=1e-3)


def test_ascendant_equator_aries_mc():
    # 0° Aries culminating at the equator -> 0° Cancer rising
    assert ascendant_tropical(0.0, 0.0, 23.44) == pytest.approx(90.0, abs=1e-6)


def test_nakshatra_and_pada():
    assert nakshatra(0.0) == (0, 1)
    assert nakshatra(359.99) == (26, 4)
    assert nakshatra(13.34) == (1, 1)


def test_house_and_navamsa():
    assert house_from(0, 0) == 1 and house_from(11, 0) == 2 and house_from(3, 0) == 10
    assert navamsa_sign(0.0) == 0      # Aries -> Aries
    assert navamsa_sign(30.0) == 9     # Taurus 0° -> Capricorn
    assert navamsa_sign(359.9) == 11   # Pisces end -> Pisces


def test_vimshottari_spans_120_years():
    periods = vimshottari(moon_lon=100.0, birth=BIRTH)
    years = (periods[-1].end - periods[0].start).days / 365.25
    assert years == pytest.approx(120, abs=1e-6)
    assert periods[0].start <= BIRTH < periods[0].end
    # 100° is Pushya (index 7) -> Saturn
    assert periods[0].lord == DASHA_ORDER[7 % 9][0] == "saturn"


def test_antardashas_fill_mahadasha():
    maha = vimshottari(10.0, BIRTH)[1]
    subs = antardashas(maha)
    assert subs[0].lord == maha.lord and subs[0].start == maha.start
    assert abs((subs[-1].end - maha.end).total_seconds()) < 1
    assert current_dasha(10.0, BIRTH, BIRTH) is not None


def _chart(**signs):
    planets = {p: Placement(s * 30 + 5) for p, s in signs.items()}
    return Chart(BIRTH, 0, 0, 24.0, ascendant=5.0, planets=planets)  # lagna Aries


def test_rules_load_and_fire():
    rules = load_rules()
    assert {"gajakesari", "hamsa"} <= {r.id for r in rules}
    c = _chart(sun=4, moon=3, mars=6, mercury=4, jupiter=3, venus=1, saturn=8, rahu=2, ketu=8)
    ids = {r.id for r in fired(c, rules)}
    assert "gajakesari" in ids        # Jupiter with Moon
    assert "hamsa" in ids             # Jupiter in Cancer, 4th from Aries lagna
    assert "budhaditya" in ids
    assert "malavya" not in ids       # Venus in Taurus but 2nd house


def test_dsl_combinators():
    ctx = Context({"lagna": 0, "moon": 3, "mars": 3})
    assert evaluate({"any": [{"same_sign": ["moon", "mars"]}, {"in_house": {"planet": "moon", "houses": [1]}}]}, ctx)
    assert not evaluate({"not": {"same_sign": ["moon", "mars"]}}, ctx)


def test_offline_geocoding_and_tz():
    p = find_place("Pune, IN")
    assert p and p.tz == "Asia/Kolkata"
    assert local_to_utc(datetime(1990, 8, 15, 14, 30), p.tz) == datetime(1990, 8, 15, 9, 0, tzinfo=timezone.utc)
    # historical US DST
    assert local_to_utc(datetime(1990, 7, 1, 12, 0), "America/Chicago").hour == 17


@pytest.mark.skipif(not os.path.exists(os.environ.get("SAMAY_EPHEMERIS", "data/de440s.bsp")),
                    reason="ephemeris file not present")
def test_full_chart_smoke():
    from samay.ephemeris import compute_chart

    c = compute_chart(datetime(2000, 1, 1, 12, tzinfo=timezone.utc), 18.52, 73.86)
    # Sun near 280.4° tropical at J2000 -> ~256.5° sidereal (Sagittarius)
    assert c.planets["sun"].longitude == pytest.approx(256.5, abs=0.2)
