from datetime import date
from pathlib import Path

import pytest
import yaml

from samay.engine import entries
from samay.engine.entries import LEVELS, Entry, answers_for, is_topic, load_entries


def raw(**changes):
    base = {
        "id": "e1", "topic": "planet:sun", "english": "Our own words.",
        "citation": {"text": "Brihat Jataka", "chapter": 2, "verse": 1, "edition": "Iyer 1885"},
        "verification": {"level": "unchecked"},
    }
    base.update(changes)
    return base


def write(tmp_path, *items) -> Path:
    (tmp_path / "e.yaml").write_text(yaml.safe_dump(list(items), allow_unicode=True))
    load_entries.cache_clear()
    return tmp_path


CHECKED = {"level": "translation-checked", "checked_by": "Harshad", "checked_on": date(2026, 11, 9),
           "against": "Iyer 1885 (public domain)"}


def test_shipped_entries_directory_loads():
    load_entries.cache_clear()
    assert all(isinstance(e, Entry) for e in load_entries())


def test_unchecked_entries_are_stored_but_never_served(tmp_path):
    d = write(tmp_path, raw())
    assert len(load_entries(d)) == 1 and answers_for("planet:sun", d) == []


def test_checked_entries_are_served_best_checked_first(tmp_path):
    scholar = {"level": "sanskrit-checked", "checked_by": "Scholar", "checked_on": date(2026, 11, 10)}
    d = write(tmp_path, raw(id="a", verification=CHECKED), raw(id="b", verification=scholar), raw(id="c"))
    assert [e.id for e in answers_for("planet:sun", d)] == ["b", "a"]
    assert answers_for("planet:moon", d) == []


@pytest.mark.parametrize(
    "bad,message",
    [
        ({"topic": "What does my Saturn mean?"}, "topic"),
        ({"verification": {"level": "trusted"}}, "level"),
        ({"verification": {"level": "translation-checked"}}, "checked_by"),
        ({"verification": {"level": "translation-checked", "checked_by": "H", "checked_on": date(2026, 1, 1)}}, "against"),
        ({"verification": {"level": "sanskrit-checked", "checked_by": "H"}}, "checked_on"),
        ({"citation": {"text": "Brihat Jataka"}}, "citation"),
        ({"verse": {"devanagari": "x"}}, "devanagari and roman"),
    ],
)
def test_malformed_or_under_verified_entries_are_rejected(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        load_entries(write(tmp_path, raw(**bad)))


def test_missing_fields_and_duplicate_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        load_entries(write(tmp_path, {"id": "x"}))
    with pytest.raises(ValueError, match="duplicate"):
        load_entries(write(tmp_path, raw(), raw()))


def test_a_verse_is_shown_only_if_its_text_was_checked_and_the_entry_is_checked(tmp_path):
    verse = {"devanagari": "सूर्यः", "roman": "sūryaḥ", "text_checked": False}
    d = write(tmp_path, raw(id="a", verification=CHECKED, verse=verse),
              raw(id="b", verification=CHECKED, verse={**verse, "text_checked": True}),
              raw(id="c", verse={**verse, "text_checked": True}))
    by_id = {e.id: e for e in load_entries(d)}
    assert [by_id[i].shows_verse for i in "abc"] == [False, True, False]


def test_citation_text_names_the_level():
    e = entries._parse(raw(verification=CHECKED), "t")
    assert e.citation_text() == "Brihat Jataka 2.1 (translation-checked)"
    assert LEVELS.index("sanskrit-checked") > LEVELS.index("translation-checked")


@pytest.mark.parametrize("good", ["dasha:saturn", "planet:sun", "transit:saturn:11", "yoga"])
def test_topic_keys(good):
    assert is_topic(good)


@pytest.mark.parametrize("bad", ["", "Dasha:Saturn", "will I marry this year", "a:b:c:d:e", "x" * 70, "dasha:sat urn"])
def test_free_text_is_not_a_topic(bad):
    assert not is_topic(bad)
