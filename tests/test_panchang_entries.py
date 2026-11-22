from samay import service
from samay.engine import entries


def test_shipped_panchang_entries_load_and_are_hidden_until_checked():
    found = [e for e in entries.load_entries() if e.id.startswith("panchang-")]
    assert {e.topic for e in found} == {"nakshatra:bharani", "nakshatra:krittika"}
    assert all(e.citation["text"] == "Brihat Samhita" and e.citation["chapter"] == 98 for e in found)
    assert all(not e.servable for e in found)  # unchecked until Task 13
    assert service.observance_explanation("bharani") == []


def test_wording_follows_the_text_and_gives_no_avoid_instruction():
    banned = ("avoid", "inauspicious", "auspicious", "good", "bad")
    for e in (e for e in entries.load_entries() if e.id.startswith("panchang-")):
        assert not any(w in e.english.lower() for w in banned)
