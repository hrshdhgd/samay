from datetime import datetime, timezone

import pytest

from samay.engine.errors import UnknownProfile
from samay.engine.paths import PROFILES_DIR
from samay.engine.profiles import DEFAULT_PROFILE, load_profile
from samay.engine.rules import load_rules
from samay.engine.vedic import vimshottari


def test_default_profile_loads_unvalidated():
    p = load_profile(DEFAULT_PROFILE)
    assert (p.ayanamsa, p.node, p.houses, p.dasha_year_days) == ("lahiri_mean", "mean", "whole_sign", 365.25)
    assert p.validated is False
    assert p.schools == ("parashari",)
    assert len(p.sha256) == 12 and p.sha256 == load_profile(DEFAULT_PROFILE).sha256


def test_unknown_profile():
    with pytest.raises(UnknownProfile):
        load_profile("no-such-profile")


def test_unsupported_house_system_rejected(tmp_path):
    text = (PROFILES_DIR / f"{DEFAULT_PROFILE}.yaml").read_text().replace("whole_sign", "placidus")
    text = text.replace(f"id: {DEFAULT_PROFILE}", "id: kp-test")
    (tmp_path / "kp-test.yaml").write_text(text)
    with pytest.raises(ValueError, match="houses"):
        load_profile("kp-test", tmp_path)


def test_rules_filtered_by_school():
    assert load_rules(schools=["parashari"])
    assert load_rules(schools=["jaimini"]) == []


def test_dasha_year_length_is_configurable():
    birth = datetime(1990, 8, 15, 9, tzinfo=timezone.utc)
    p365 = vimshottari(100.0, birth)
    p360 = vimshottari(100.0, birth, year_days=360.0)
    assert (p360[-1].end - p360[0].start).days < (p365[-1].end - p365[0].start).days
