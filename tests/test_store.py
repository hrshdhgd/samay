import sqlite3

import pytest

from samay.models import BirthInput
from samay.store import DRAFT_TTL_SECONDS, MIGRATIONS, Store

BIRTH = BirthInput("1952-08-15", "06:30", "Pune", "1259229", None, "parashari-lahiri", "Wagholi")


def test_user_round_trip_and_forget(tmp_path):
    s = Store(tmp_path / "t.db")
    assert s.get_user(1) is None
    s.save_user(1, BIRTH)
    assert s.get_user(1) == BIRTH
    s.save_draft(1, {"step": "date"})
    s.forget(1)
    assert s.get_user(1) is None and s.get_draft(1) is None


def test_resaving_replaces(tmp_path):
    s = Store(tmp_path / "t.db")
    s.save_user(1, BIRTH)
    s.save_user(1, BirthInput("1960-01-01", "12:00", "Mumbai"))
    assert s.get_user(1).place_text == "Mumbai"


def test_draft_expires_after_thirty_minutes_and_is_deleted(tmp_path):
    s = Store(tmp_path / "t.db")
    s.save_draft(1, {"step": "time"}, now=1000)
    assert s.get_draft(1, now=1000 + DRAFT_TTL_SECONDS) == {"step": "time"}
    assert s.get_draft(1, now=1000 + DRAFT_TTL_SECONDS + 1) is None
    with sqlite3.connect(tmp_path / "t.db") as c:
        assert c.execute("SELECT count(*) FROM drafts").fetchone()[0] == 0


def test_purge_removes_only_expired_drafts(tmp_path):
    s = Store(tmp_path / "t.db")
    s.save_draft(1, {"a": 1}, now=0)
    s.save_draft(2, {"b": 2}, now=DRAFT_TTL_SECONDS)
    assert s.purge_expired(now=DRAFT_TTL_SECONDS + 10) == 1
    assert s.get_draft(2, now=DRAFT_TTL_SECONDS + 10) == {"b": 2}


def test_schema_is_versioned_and_reopening_keeps_data(tmp_path):
    path = tmp_path / "t.db"
    Store(path).save_user(1, BIRTH)
    assert Store(path).get_user(1) == BIRTH
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_home_round_trip_keeps_the_brief_setting_when_the_city_changes(tmp_path):
    from samay.store import Home

    s = Store(tmp_path / "t.db")
    assert s.get_home(1) is None
    s.save_home(1, "Maplewood, MN", "111")
    assert s.get_home(1) == Home("Maplewood, MN", "111")
    s.set_brief(1, 7)
    s.mark_brief_sent(1, "2026-11-09")
    s.save_home(1, "Pune", "222")
    assert s.get_home(1) == Home("Pune", "222", 7, None)  # new city: same hour, "sent today" reset


def test_brief_on_off_and_listing(tmp_path):
    s = Store(tmp_path / "t.db")
    s.save_home(1, "A", "1")
    s.save_home(2, "B", "2")
    s.set_brief(1, 8)
    assert [(c, h.brief_hour) for c, h in s.briefs_enabled()] == [(1, 8)]
    s.mark_brief_sent(1, "2026-11-09")
    assert s.get_home(1).brief_last == "2026-11-09"
    s.set_brief(1, None)
    assert s.briefs_enabled() == []


def test_forget_also_removes_the_home(tmp_path):
    s = Store(tmp_path / "t.db")
    s.save_home(1, "A", "1")
    s.save_user(1, BIRTH)
    s.forget(1)
    assert s.get_home(1) is None and s.get_user(1) is None


def test_existing_database_upgrades_in_place(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:  # a database created by the first version of the schema
        c.executescript(MIGRATIONS[0])
        c.execute("INSERT INTO users VALUES (1,'1952-08-15','06:30','Pune',NULL,NULL,'parashari-lahiri',NULL,0)")
        c.execute("PRAGMA user_version = 1")
    s = Store(path)
    assert s.get_user(1).place_text == "Pune"
    s.save_home(1, "Maplewood", "5")
    assert s.get_home(1).place_id == "5"


def test_unanswered_topics_are_counted_without_any_wording_or_chat_id(tmp_path):
    s = Store(tmp_path / "t.db")
    for topic in ("dasha:saturn", "dasha:saturn", "planet:rahu", "dasha:saturn"):
        s.record_miss(topic)
    assert s.top_misses() == [("dasha:saturn", 3), ("planet:rahu", 1)]
    assert s.top_misses(limit=1) == [("dasha:saturn", 3)]
    with sqlite3.connect(tmp_path / "t.db") as c:
        assert [r[1] for r in c.execute("PRAGMA table_info(topic_misses)")] == ["topic", "count"]


@pytest.mark.parametrize("words", ["will my son marry this year?", "Saturn", "dasha:Saturn", ""])
def test_free_text_is_refused_as_a_topic(tmp_path, words):
    s = Store(tmp_path / "t.db")
    with pytest.raises(ValueError):
        s.record_miss(words)
    assert s.top_misses() == []


def test_forget_does_not_touch_the_anonymous_topic_counts(tmp_path):
    s = Store(tmp_path / "t.db")
    s.record_miss("dasha:saturn")
    s.forget(1)
    assert s.top_misses() == [("dasha:saturn", 1)]
