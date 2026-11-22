from samay import service
from samay.engine import entries


def test_shipped_panchang_entries_load_and_only_checked_ones_are_servable():
    found = {e.id: e for e in entries.load_entries() if e.id.startswith("panchang-")}
    assert {e.topic for e in found.values()} == {
        "nakshatra:bharani",
        "nakshatra:krittika",
        "observance:pradosha",
    }
    nakshatra = [e for e in found.values() if e.topic.startswith("nakshatra:")]
    assert all(e.citation["text"] == "Brihat Samhita" and e.citation["chapter"] == 98 for e in nakshatra)
    assert all(not e.servable for e in nakshatra)  # still unchecked: hidden
    assert found["panchang-pradosha-skanda-brahma-6-5"].servable  # translation-checked
    assert {e.id for e in found.values() if e.servable} == {"panchang-pradosha-skanda-brahma-6-5"}
    assert service.nakshatra_explanation("bharani") == []


def test_wording_follows_the_text_and_gives_no_avoid_instruction():
    banned = ("avoid", "inauspicious", "auspicious", "good", "bad")
    for e in (e for e in entries.load_entries() if e.id.startswith("panchang-")):
        assert not any(w in e.english.lower() for w in banned)
