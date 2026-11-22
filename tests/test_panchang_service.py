from datetime import UTC, date, datetime, timedelta

import pytest

from samay import service
from samay.engine import entries, observances, panchang_profile
from samay.engine.geo import Place
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE = Place("pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458)


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    """A copy of the panchang profile that tests may edit; the service reads it through this directory."""
    import yaml

    from samay.engine.paths import PROFILES_DIR

    for name in ("panchang-family.yaml", "tulu.yaml"):
        (tmp_path / name).write_text((PROFILES_DIR / name).read_text())
    monkeypatch.setattr(service, "PANCHANG_PROFILES_DIR", tmp_path)
    panchang_profile.load_panchang_profile.cache_clear()

    def edit(**top):
        raw = yaml.safe_load((tmp_path / "panchang-family.yaml").read_text())
        raw.update(top)
        (tmp_path / "panchang-family.yaml").write_text(yaml.safe_dump(raw))
        panchang_profile.load_panchang_profile.cache_clear()

    yield edit
    panchang_profile.load_panchang_profile.cache_clear()


def test_report_has_local_facts_and_the_tulu_date():
    r = service.panchang_report(PUNE, date(2026, 11, 21))
    assert r.facts.tithi.name == "Shukla Dwadashi" and r.facts.sunrise.strftime("%H:%M") == "06:44"
    assert (r.tulu.month, r.tulu.day) == ("Jarde", 5)


def test_unverified_rules_make_no_day_claim_and_say_so():
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert r.observances == () and r.claims_withheld


def test_a_verified_rule_with_no_tradition_asks_for_one(profile_dir):
    import yaml

    raw = yaml.safe_load((service.PANCHANG_PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["ekadashi"]["verified"] = True
    profile_dir(observances=raw["observances"])
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert r.needs_sampradaya and r.observances == ()


def test_a_verified_rule_and_a_set_tradition_name_the_day_with_its_alternate(profile_dir):
    import yaml

    raw = yaml.safe_load((service.PANCHANG_PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["ekadashi"]["verified"] = True
    profile_dir(observances=raw["observances"], sampradaya="smarta")
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    (o,) = [x for x in r.observances if x.name == "ekadashi"]
    assert o.primary == date(2026, 11, 20) and o.kind == "kshaya"
    # The 21st is both the kshaya alternate and the Madhva day: shown once, with both reasons.
    assert (date(2026, 11, 21), "kshaya and madhva convention") in o.alternates
    assert len({d for d, _ in o.alternates}) == len(o.alternates)
    assert o.explanation is None  # no checked explanation exists yet


def test_an_alternate_day_named_for_several_reasons_is_listed_once():
    first, second = date(2026, 11, 21), date(2026, 11, 22)
    found = observances.Observance(
        date(2026, 11, 20), "kshaya",
        (observances.Alternate(first, "kshaya"), observances.Alternate(second, "calculation"),
         observances.Alternate(first, "madhva convention")),
        datetime(2026, 11, 19, tzinfo=UTC), datetime(2026, 11, 20, tzinfo=UTC),
    )
    day = service._as_day("ekadashi", "Ekadashi", found)
    assert day.alternates == ((first, "kshaya and madhva convention"), (second, "calculation"))


def test_next_observance_reports_why_it_cannot_name_a_day():
    n = service.next_observance_report(PUNE, "ekadashi", date(2026, 11, 6))
    assert n.found is None and not n.claim_available


def test_reference_place_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    assert service.reference_place() is None
    monkeypatch.setenv("SAMAY_REFERENCE_PLACE", "Pune, IN")
    assert service.reference_place().name == "Pune"


def test_explanations_are_only_those_of_checked_entries(tmp_path):
    assert service.observance_explanation("bharani", directory=tmp_path) == []


def _bharani_day() -> date:
    from samay.engine import panchang

    site = service._site(PUNE)
    profile = service._panchang_profile()
    for n in range(120):
        d = date(2026, 11, 1) + timedelta(days=n)
        facts = panchang.day_facts(site, d, profile.ayanamsa, profile.sunrise_definition)
        if facts and facts.nakshatra.name == "Bharani":
            return d
    raise AssertionError("no Bharani sunrise found")


def _write_bharani(tmp_path, level):
    import yaml

    verification = {"level": level}
    if level != "unchecked":
        verification |= {"checked_by": "Harshad", "checked_on": date(2026, 11, 22), "against": "test copy"}
    (tmp_path / "e.yaml").write_text(yaml.safe_dump([{
        "id": "panchang-bharani-test", "topic": "nakshatra:bharani", "system": "any",
        "english": "A description of the star's character.",
        "citation": {"text": "Brihat Samhita", "chapter": 98, "verse": "8", "edition": "test"},
        "verification": verification}]))
    entries.load_entries.cache_clear()


def test_a_checked_nakshatra_entry_is_shown_once_in_the_day_answer(tmp_path, monkeypatch):
    from samay.render import panchang as words

    day = _bharani_day()
    monkeypatch.setattr(entries, "ENTRIES_DIR", tmp_path)
    _write_bharani(tmp_path, "translation-checked")
    text = words.render_day(service.panchang_report(PUNE, day), day)
    assert text.count("A description of the star's character.") == 1
    entries.load_entries.cache_clear()


def test_an_unchecked_nakshatra_entry_adds_nothing(tmp_path, monkeypatch):
    day = _bharani_day()
    monkeypatch.setattr(entries, "ENTRIES_DIR", tmp_path)
    _write_bharani(tmp_path, "unchecked")
    assert not any(o.name == "bharani" for o in service.panchang_report(PUNE, day).observances)
    entries.load_entries.cache_clear()
