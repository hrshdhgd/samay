import sqlite3
import stat

import pytest
from click.testing import CliRunner

from samay import crypto
from samay.cli import cli
from samay.models import BirthInput
from samay.store import MIGRATIONS, Store

SECRET = BirthInput("1952-08-15", "06:30", "Kolhapur", "1266285", 1, "parashari-lahiri", "Wagholi")
WORDS = ("1952-08-15", "06:30", "Kolhapur", "1266285", "Wagholi", "Maplewood", "5036588")


def raw_dump(path) -> str:
    with sqlite3.connect(path) as c:
        return "\n".join(c.iterdump())


def key() -> str:
    return crypto.generate_key()


def test_nothing_personal_is_readable_on_disk(tmp_path):
    s = Store(tmp_path / "t.db", key())
    s.save_user(1, SECRET)
    s.save_draft(1, {"step": "place", "date_text": "1952-08-15", "place_text": "Kolhapur"})
    s.save_home(1, "Maplewood", "5036588")
    dump = raw_dump(tmp_path / "t.db")
    for word in WORDS:
        assert word not in dump, word
    assert dump.count(crypto.PREFIX) >= 9  # users (6) + drafts (1) + homes (2)
    assert "parashari-lahiri" in dump  # the profile name is not personal and stays readable


def test_everything_still_round_trips(tmp_path):
    s = Store(tmp_path / "t.db", key())
    s.save_user(1, SECRET)
    s.save_user(2, BirthInput("1990-08-15", "14:30", "Pune"))
    s.save_draft(1, {"step": "time", "options": ["a", "b"]})
    s.save_home(1, "Maplewood", "5036588")
    s.set_brief(1, 7)
    assert s.get_user(1) == SECRET
    assert s.get_user(2) == BirthInput("1990-08-15", "14:30", "Pune")  # None fields stay None, fold too
    assert s.get_draft(1) == {"step": "time", "options": ["a", "b"]}
    home = s.get_home(1)
    assert (home.place_text, home.place_id, home.brief_hour) == ("Maplewood", "5036588", 7)
    assert [c for c, _ in s.briefs_enabled()] == [1]


def test_rekey_moves_everything_to_the_new_key_and_the_old_key_stops_working(tmp_path):
    old, new = key(), key()
    s = Store(tmp_path / "t.db", old)
    s.save_user(1, SECRET)
    s.save_draft(1, {"step": "date"})
    s.save_home(1, "Maplewood", "5036588")
    s.rekey(new)
    assert s.get_user(1) == SECRET  # the open store carries on with the new key
    with pytest.raises(crypto.StoreKeyError):
        Store(tmp_path / "t.db", old)
    again = Store(tmp_path / "t.db", new)
    assert again.get_user(1) == SECRET and again.get_draft(1) == {"step": "date"}
    assert again.get_home(1).place_text == "Maplewood"
    assert all(w not in raw_dump(tmp_path / "t.db") for w in WORDS)


def test_a_failed_rekey_changes_nothing(tmp_path):
    k = key()
    s = Store(tmp_path / "t.db", k)
    s.save_user(1, SECRET)
    before = raw_dump(tmp_path / "t.db")
    with pytest.raises(crypto.StoreKeyError):
        s.rekey("not-a-key")
    assert raw_dump(tmp_path / "t.db") == before and Store(tmp_path / "t.db", k).get_user(1) == SECRET


def test_the_test_suite_runs_on_an_isolated_database():
    from samay.engine.paths import DATA_DIR

    assert Store().path != DATA_DIR / "samay.db" and "isolated" in str(Store().path)


def test_a_wrong_key_is_refused_when_the_store_opens(tmp_path):
    first = key()
    Store(tmp_path / "t.db", first).save_user(1, SECRET)
    with pytest.raises(crypto.StoreKeyError, match="does not match"):
        Store(tmp_path / "t.db", key())
    assert Store(tmp_path / "t.db", first).get_user(1) == SECRET  # the right key still works


def test_tampered_ciphertext_is_refused_not_misread(tmp_path):
    s = Store(tmp_path / "t.db", key())
    s.save_user(1, SECRET)
    with sqlite3.connect(tmp_path / "t.db") as c:
        c.execute("UPDATE users SET place_text = ? WHERE chat_id = 1",
                  (crypto.PREFIX + "gAAAAAB" + "A" * 80,))
    with pytest.raises(crypto.StoreKeyError):
        s.get_user(1)


def test_plaintext_from_an_older_version_is_encrypted_when_the_store_opens(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:  # the first schema, with plaintext rows, as the early bot wrote them
        c.executescript(MIGRATIONS[0])
        c.execute("INSERT INTO users VALUES (1,'1952-08-15','06:30','Kolhapur','1266285',1,'parashari-lahiri','Wagholi',0)")
        c.execute("INSERT INTO drafts VALUES (1,'{\"step\": \"date\", \"place_text\": \"Kolhapur\"}', 0)")
        c.execute("PRAGMA user_version = 1")
    k = key()
    s = Store(path, k)
    assert s.get_user(1) == SECRET
    assert s.get_draft(1, now=1) == {"step": "date", "place_text": "Kolhapur"}
    dump = raw_dump(path)
    assert "Kolhapur" not in dump and "1952-08-15" not in dump
    sealed = raw_dump(path)
    Store(path, k)  # opening again must not re-encrypt (idempotent)
    assert raw_dump(path) == sealed


def test_database_file_is_made_private(tmp_path):
    k = key()
    Store(tmp_path / "u.db", k)
    (tmp_path / "u.db").chmod(0o644)
    Store(tmp_path / "u.db", k)
    assert stat.S_IMODE((tmp_path / "u.db").stat().st_mode) == 0o600


def test_environment_key_wins_and_creates_no_file(tmp_path):
    k = key()
    f = tmp_path / "samay.key"
    assert crypto.resolve_key({crypto.KEY_ENV: f" {k} "}, f) == k and not f.exists()


def test_key_file_is_created_private_and_reused(tmp_path, caplog):
    f = tmp_path / "keys" / "samay.key"
    first = crypto.resolve_key({}, f)
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and crypto.Cipher(first)
    assert crypto.resolve_key({}, f) == first
    assert "created a local database key" in caplog.text and first not in caplog.text


def test_a_malformed_key_is_reported_clearly(tmp_path):
    with pytest.raises(crypto.StoreKeyError, match="samay keygen"):
        Store(tmp_path / "t.db", "not-a-key")


def test_values_without_the_prefix_are_treated_as_legacy_plaintext():
    c = crypto.Cipher(key())
    assert c.decrypt("hello") == "hello" and c.decrypt(c.encrypt("hello")) == "hello"
    assert c.encrypt("hello") != c.encrypt("hello")  # a fresh nonce each time


def test_keygen_prints_a_usable_unique_key():
    out = [CliRunner().invoke(cli, ["keygen"]).output.strip() for _ in range(2)]
    assert out[0] != out[1] and all(crypto.Cipher(k) for k in out)


def test_backup_is_private_encrypted_readable_and_never_overwrites(tmp_path, monkeypatch):
    k = key()
    monkeypatch.setenv("SAMAY_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv(crypto.KEY_ENV, k)
    Store().save_user(1, SECRET)
    out = tmp_path / "copy.db"
    r = CliRunner().invoke(cli, ["backup", "--out", str(out)])
    assert r.exit_code == 0 and stat.S_IMODE(out.stat().st_mode) == 0o600
    assert all(w not in raw_dump(out) for w in WORDS)
    assert Store(out, k).get_user(1) == SECRET
    again = CliRunner().invoke(cli, ["backup", "--out", str(out)])
    assert again.exit_code == 1 and "refusing to overwrite" in again.output


def test_the_bot_refuses_to_start_with_a_bad_key(monkeypatch, tmp_path):
    from samay.bot import app as bot

    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("SAMAY_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("SAMAY_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv(crypto.KEY_ENV, "garbage")
    with pytest.raises(SystemExit, match="cannot open the database"):
        bot.main()


def test_topic_counts_stay_anonymous_and_unencrypted(tmp_path):
    s = Store(tmp_path / "t.db", key())
    s.record_miss("dasha:saturn")
    assert "dasha:saturn" in raw_dump(tmp_path / "t.db") and s.top_misses() == [("dasha:saturn", 1)]


