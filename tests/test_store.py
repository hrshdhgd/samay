import sqlite3

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
