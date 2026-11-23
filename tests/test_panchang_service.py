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
    assert r.facts.tithi.name == "Shukla Dwadashi" and r.facts.sunrise.strftime("%H:%M") == "06:45"
    assert (r.tulu.month, r.tulu.day) == ("Jaarde", 5)


def _edit_rules(profile_dir, *, verified=None, **top):
    """Edit the temporary copy of the shipped profile: set every observance's verified flag, plus top-level fields."""
    import yaml

    raw = yaml.safe_load((service.PANCHANG_PROFILES_DIR / "panchang-family.yaml").read_text())
    if verified is not None:
        for spec in raw["observances"].values():
            spec["verified"] = verified
    profile_dir(observances=raw["observances"], **top)


def test_the_shipped_profile_names_days_end_to_end():
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert not r.claims_withheld and not r.needs_sampradaya
    (o,) = r.observances  # Ekadashi only: no Pradosha, Purnima or Amavasya on this day
    assert o.name == "ekadashi" and o.primary == date(2026, 11, 20) and o.kind == "kshaya"
    assert (date(2026, 11, 21), "kshaya and madhva convention") in o.alternates
    assert o.explanation is None  # no checked Ekadashi entry
    # The 21st is only an alternate of the 20th's Ekadashi, never a primary day of its own.
    assert all(
        x.primary != date(2026, 11, 21) for x in service.panchang_report(PUNE, date(2026, 11, 21)).observances
    )


def test_the_shipped_pradosha_window_is_the_one_the_profile_states():
    rule = panchang_profile.load_panchang_profile().observances["pradosha"].rules["all"]
    assert (rule.anchor, rule.start_minutes, rule.end_minutes) == ("sunset", 0, 144)


def test_unverified_rules_make_no_day_claim_and_say_so(profile_dir):
    _edit_rules(profile_dir, verified=False)
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert r.observances == () and r.claims_withheld


def test_a_verified_rule_with_no_tradition_asks_for_one(profile_dir):
    _edit_rules(profile_dir, verified=True, sampradaya=None)
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert r.needs_sampradaya and r.observances == ()


def test_a_verified_rule_and_a_set_tradition_name_the_day_with_its_alternate(
    profile_dir,
):
    _edit_rules(profile_dir, verified=True, sampradaya="smarta")
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    (o,) = [x for x in r.observances if x.name == "ekadashi"]
    assert o.primary == date(2026, 11, 20) and o.kind == "kshaya"
    # The 21st is both the kshaya alternate and the Madhva day: shown once, with both reasons.
    assert (date(2026, 11, 21), "kshaya and madhva convention") in o.alternates
    assert len({d for d, _ in o.alternates}) == len(o.alternates)
    assert o.explanation is None  # no checked Ekadashi entry exists


def test_an_alternate_day_named_for_several_reasons_is_listed_once():
    first, second = date(2026, 11, 21), date(2026, 11, 22)
    found = observances.Observance(
        date(2026, 11, 20),
        "kshaya",
        (
            observances.Alternate(first, "kshaya"),
            observances.Alternate(second, "calculation"),
            observances.Alternate(first, "madhva convention"),
        ),
        datetime(2026, 11, 19, tzinfo=UTC),
        datetime(2026, 11, 20, tzinfo=UTC),
    )
    day = service._as_day("ekadashi", "Ekadashi", found)
    assert day.alternates == (
        (first, "kshaya and madhva convention"),
        (second, "calculation"),
    )


def test_next_observance_reports_why_it_cannot_name_a_day(profile_dir):
    _edit_rules(profile_dir, verified=False)
    n = service.next_observance_report(PUNE, "ekadashi", date(2026, 11, 6))
    assert n.found is None and not n.claim_available
    _edit_rules(profile_dir, verified=True, sampradaya=None)
    n = service.next_observance_report(PUNE, "ekadashi", date(2026, 11, 6))
    assert n.found is None and n.needs_sampradaya


def test_next_observance_names_the_day_from_the_shipped_profile():
    n = service.next_observance_report(PUNE, "ekadashi", date(2026, 11, 6))
    assert n.claim_available and n.found.primary == date(2026, 11, 20) and n.found.explanation is None
    p = service.next_observance_report(PUNE, "pradosha", date(2026, 11, 6))
    assert p.found.primary == date(2026, 11, 6)
    (checked,) = entries.answers_for("observance:pradosha")
    assert p.found.explanation == checked.english


def test_shipped_pradosha_entry_is_servable_and_bharani_is_not():
    (e,) = entries.answers_for("observance:pradosha")
    assert e.servable and e.id == "panchang-pradosha-skanda-brahma-6-5"
    assert not any(w in e.english.lower() for w in ("avoid", "inauspicious", "good fortune", "will bring"))
    assert service.nakshatra_explanation("bharani") == []


def test_reference_place_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    assert service.reference_place() is None
    monkeypatch.setenv("SAMAY_REFERENCE_PLACE", "Pune, IN")
    assert service.reference_place().name == "Pune"


def test_explanations_are_only_those_of_checked_entries(tmp_path):
    assert service.nakshatra_explanation("bharani", directory=tmp_path) == []


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
        verification |= {
            "checked_by": "Harshad",
            "checked_on": date(2026, 11, 22),
            "against": "test copy",
        }
    (tmp_path / "e.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "panchang-bharani-test",
                    "topic": "nakshatra:bharani",
                    "system": "any",
                    "english": "A description of the star's character.",
                    "citation": {
                        "text": "Brihat Samhita",
                        "chapter": 98,
                        "verse": "8",
                        "edition": "test",
                    },
                    "verification": verification,
                }
            ]
        )
    )
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


def test_nakshatra_and_observance_explanations_use_their_own_topics(tmp_path):
    import yaml

    checked = {
        "level": "translation-checked",
        "checked_by": "Harshad",
        "checked_on": date(2026, 11, 22),
        "against": "test copy",
    }
    (tmp_path / "e.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": f"panchang-{topic.replace(':', '-')}-test",
                    "topic": topic,
                    "system": "any",
                    "english": f"About {topic}.",
                    "citation": {
                        "text": "Brihat Samhita",
                        "chapter": 98,
                        "verse": "1",
                        "edition": "test",
                    },
                    "verification": checked,
                }
                for topic in ("nakshatra:rohini", "observance:ekadashi")
            ]
        )
    )
    entries.load_entries.cache_clear()
    assert service.nakshatra_explanation("rohini", directory=tmp_path) == ["About nakshatra:rohini."]
    assert service.observance_explanation("rohini", directory=tmp_path) == []
    assert service.observance_explanation("ekadashi", directory=tmp_path) == ["About observance:ekadashi."]
    assert service.nakshatra_explanation("ekadashi", directory=tmp_path) == []
    entries.load_entries.cache_clear()


# --- lists of observance days over a range ------------------------------------------------------

MANGALURU = Place(
    "1263780",
    "Mangaluru",
    "IN",
    "19",
    "575",
    12.91723,
    74.85603,
    "Asia/Kolkata",
    499487,
)


def test_a_list_names_every_verified_observance_in_the_range():
    r = service.observance_list_report(MANGALURU, date(2026, 11, 22), date(2026, 12, 31))
    assert not r.too_long and not r.needs_sampradaya and r.withheld == ()
    assert (
        r.labels
        == (
            "Ekadashi",
            "Pradosha",
            "Purnima",
            "Amavasya",
            "Sankashti Chaturthi",
        )
        and not r.filtered
    )
    primaries = [(o.primary, o.name) for o in r.days]
    assert primaries == sorted(primaries)
    # The Tulu Panchanga app for Mangaluru (2026 festival list) gives these days for the same span.
    assert set(primaries) >= {
        (date(2026, 11, 22), "pradosha"),
        (date(2026, 11, 24), "purnima"),
        (date(2026, 12, 4), "ekadashi"),
        (date(2026, 12, 8), "amavasya"),
        (date(2026, 12, 20), "ekadashi"),
        (date(2026, 12, 24), "purnima"),
        (date(2026, 11, 27), "sankashti"),
        (date(2026, 12, 26), "sankashti"),
    }
    assert all(o.explanation is None for o in r.days)  # a list carries no explanation text


def test_a_list_can_be_limited_to_some_observances():
    r = service.observance_list_report(
        MANGALURU, date(2026, 12, 1), date(2026, 12, 31), ("ekadashi", "pradosha")
    )
    assert r.filtered and r.labels == ("Ekadashi", "Pradosha")
    assert {o.name for o in r.days} == {"ekadashi", "pradosha"}


def test_a_list_never_names_a_day_from_an_unverified_rule(profile_dir):
    _edit_rules(profile_dir, verified=False)
    r = service.observance_list_report(MANGALURU, date(2026, 12, 1), date(2026, 12, 31))
    assert r.days == () and set(r.withheld) == {
        "Ekadashi",
        "Pradosha",
        "Purnima",
        "Amavasya",
        "Sankashti Chaturthi",
    }  # the copy's key order


def test_a_list_with_only_some_rules_verified_names_only_those(profile_dir):
    import yaml

    raw = yaml.safe_load((service.PANCHANG_PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["pradosha"]["verified"] = False
    profile_dir(observances=raw["observances"])
    r = service.observance_list_report(MANGALURU, date(2026, 12, 1), date(2026, 12, 31))
    assert r.withheld == ("Pradosha",) and r.days and all(o.name != "pradosha" for o in r.days)


def test_a_list_without_a_tradition_names_no_tradition_dependent_day(profile_dir):
    _edit_rules(profile_dir, verified=True, sampradaya=None)
    r = service.observance_list_report(MANGALURU, date(2026, 12, 1), date(2026, 12, 31))
    assert r.needs_sampradaya and all(o.name != "ekadashi" for o in r.days)


def test_a_list_longer_than_a_year_is_refused_without_working_it_out(monkeypatch):
    monkeypatch.setattr(
        observances,
        "observances_for",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError),
    )
    r = service.observance_list_report(MANGALURU, date(2026, 1, 1), date(2027, 1, 2))  # 367 days
    assert r.too_long and r.days == ()
    assert not service.observance_list_report(
        MANGALURU, date(2028, 1, 1), date(2028, 12, 31), ("x",)
    ).too_long


MANGALURU = Place("mangaluru", "Mangaluru", "IN", "Karnataka", None, 12.9141, 74.856, "Asia/Kolkata", 1)


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 12, 8), ["Amavasya"]),
        (date(2026, 12, 21), ["Bharani"]),
        (date(2026, 12, 22), ["Krittika"]),
        (date(2026, 12, 10), []),
    ],
)
def test_care_notes_follow_the_sunrise_tithi_and_nakshatra(day, expected):
    from samay.render import panchang as words

    r = service.panchang_report(MANGALURU, day)
    assert len(r.care_notes) == len(expected)
    assert all(w in t for w, t in zip(expected, r.care_notes))
    text = words.render_day(r, day)
    assert text.count(
        "Traditional guidance (muhurta tradition; we have not checked the original text)"
    ) == len(expected)


def test_care_notes_are_absent_when_the_profile_has_none(profile_dir):
    profile_dir(traditional_care=[])
    assert service.panchang_report(MANGALURU, date(2026, 12, 8)).care_notes == ()


def test_care_notes_do_not_touch_the_checked_entry_machinery():
    assert entries.answers_for("nakshatra:bharani") == []
    assert service.nakshatra_explanation("bharani") == []
