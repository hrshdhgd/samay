import pytest
import yaml

from samay.engine.panchang_profile import load_panchang_profile
from samay.engine.paths import PROFILES_DIR


def write(tmp_path, **changes):
    raw = yaml.safe_load((PROFILES_DIR / "panchang-family.yaml").read_text())
    raw.update(changes)
    (tmp_path / "panchang-family.yaml").write_text(yaml.safe_dump(raw))
    load_panchang_profile.cache_clear()
    return tmp_path


def test_shipped_profile_loads_with_the_smarta_tradition():
    p = load_panchang_profile()
    assert p.sampradaya == "smarta"
    assert set(p.observances) == {"ekadashi", "pradosha", "purnima", "amavasya"}
    assert p.observances["ekadashi"].rules["madhva"].viddha is not None
    assert p.observances["pradosha"].rules["all"].anchor == "sunset"
    assert p.observances["pradosha"].rules["all"].end_minutes == 144
    assert p.margin_minutes >= 0 and p.sunrise_definition in (
        "upper_limb",
        "disc_centre",
    )


def test_every_shipped_rule_is_verified_and_names_its_source():
    for name, spec in load_panchang_profile().observances.items():
        assert spec.verified, name
        assert spec.source.get("text") and spec.source.get("locus"), name


def test_a_profile_can_still_be_unverified_and_without_a_tradition(tmp_path):
    raw = yaml.safe_load((PROFILES_DIR / "panchang-family.yaml").read_text())
    for spec in raw["observances"].values():
        spec["verified"] = False
    p = load_panchang_profile(directory=write(tmp_path, observances=raw["observances"], sampradaya=None))
    assert p.sampradaya is None and not any(o.verified for o in p.observances.values())


@pytest.mark.parametrize(
    "field, value",
    [
        ("sampradaya", "zoroastrian"),
        ("ayanamsa", "fagan"),
        ("sunrise_definition", "moonrise"),
        ("ambiguity_margin_minutes", -1),
    ],
)
def test_bad_values_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError, match=field.split("_")[0]):
        load_panchang_profile(directory=write(tmp_path, **{field: value}))


def test_a_rule_with_a_bad_choice_is_rejected(tmp_path):
    raw = yaml.safe_load((PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["ekadashi"]["rules"]["madhva"]["on_kshaya"] = "tomorrow-ish"
    write(tmp_path, observances=raw["observances"])
    with pytest.raises(ValueError, match="on_kshaya"):
        load_panchang_profile(directory=tmp_path)


def test_shipped_margin_is_in_a_sane_band():
    assert 3 <= load_panchang_profile().margin_minutes <= 15


def test_measure_margin_script_exposes_its_three_components():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "measure_margin.py"
    spec = importlib.util.spec_from_file_location("measure_margin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert all(
        callable(getattr(module, n))
        for n in (
            "sunrise_shift_minutes",
            "boundary_shift_minutes",
            "nutation_shift_minutes",
        )
    )


def test_a_tradition_some_observance_has_no_rule_for_fails_on_load(tmp_path):
    with pytest.raises(ValueError, match="ekadashi.*vaishnava"):
        load_panchang_profile(directory=write(tmp_path, sampradaya="vaishnava"))


@pytest.mark.parametrize("tradition", ["smarta", "madhva"])
def test_a_tradition_every_observance_covers_loads(tmp_path, tradition):
    assert load_panchang_profile(directory=write(tmp_path, sampradaya=tradition)).sampradaya == tradition
