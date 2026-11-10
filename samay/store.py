"""SQLite store for the bot: saved birth details and in-progress conversations.

Birth details are kept exactly as the user entered them and re-resolved on every read, so data
corrections apply automatically. Every field that holds personal data (birth details, drafts, the
city a person lives in) is encrypted at rest (see crypto.py). Left in the clear on purpose: the
Telegram chat id (it is the row key), the chosen profile, the morning-message hour, and the
anonymous topic counts, none of which identify a birth.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from . import crypto
from .engine.entries import is_topic
from .engine.paths import DATA_DIR
from .models import BirthInput

DRAFT_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class Home:
    place_text: str  # what the person typed
    place_id: str
    brief_hour: int | None = None  # local hour for the morning message; None = off
    brief_last: str | None = None  # local date (YYYY-MM-DD) the last message was sent


MIGRATIONS = [
    """
    CREATE TABLE users (
        chat_id INTEGER PRIMARY KEY,
        date_text TEXT NOT NULL, time_text TEXT NOT NULL, place_text TEXT NOT NULL,
        place_choice TEXT, fold INTEGER, profile TEXT NOT NULL, approx_for TEXT,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE drafts (
        chat_id INTEGER PRIMARY KEY, data TEXT NOT NULL, updated_at INTEGER NOT NULL
    );
    """,
    # Where the person lives now (for sunrise-based timings) and their morning-message setting.
    """
    CREATE TABLE homes (
        chat_id INTEGER PRIMARY KEY, place_text TEXT NOT NULL, place_id TEXT NOT NULL,
        brief_hour INTEGER, brief_last TEXT
    );
    """,
    # Topics people asked about that had no sourced answer. Topics and counts only: never wording or a chat id.
    """
    CREATE TABLE topic_misses (topic TEXT PRIMARY KEY, count INTEGER NOT NULL);
    """,
    # A sealed constant, so a wrong key is caught when the store opens, not on the first read.
    """
    CREATE TABLE keycheck (id INTEGER PRIMARY KEY CHECK (id = 1), token TEXT NOT NULL);
    """,
]

# Columns holding personal data, per table (all encrypted).
SEALED = {
    "users": ("date_text", "time_text", "place_text", "place_choice", "fold", "approx_for"),
    "drafts": ("data",),
    "homes": ("place_text", "place_id"),
}
KEY_ROW = {"users": "chat_id", "drafts": "chat_id", "homes": "chat_id"}
CHECK_VALUE = "samay"


class Store:
    def __init__(self, path: str | os.PathLike | None = None, key: str | None = None):
        self.path = Path(path or os.environ.get("SAMAY_DB") or DATA_DIR / "samay.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = crypto.Cipher(key or crypto.resolve_key())
        with self._conn() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
                c.executescript(script)
                c.execute(f"PRAGMA user_version = {i}")
        self._check_key()
        self._seal_legacy_rows()
        if self.path.stat().st_mode & 0o077:  # readable by others
            self.path.chmod(0o600)  # owner-only, like the key file

    def _check_key(self) -> None:
        with self._conn() as c:
            row = c.execute("SELECT token FROM keycheck WHERE id = 1").fetchone()
            if row is None:
                c.execute("INSERT INTO keycheck VALUES (1, ?)", (self._cipher.encrypt(CHECK_VALUE),))
            elif self._cipher.decrypt(row["token"]) != CHECK_VALUE:
                raise crypto.StoreKeyError("the database key does not match this database")

    def _seal(self, value: object) -> str | None:
        return None if value is None else self._cipher.encrypt(str(value))

    def _open(self, value: object) -> str | None:
        return None if value is None else self._cipher.decrypt(str(value))

    def _seal_legacy_rows(self) -> None:
        """Encrypt any plaintext left by a version that did not encrypt. Idempotent."""
        with self._conn() as c:
            for table, columns in SEALED.items():
                for row in c.execute(f"SELECT * FROM {table}").fetchall():
                    todo = {col: self._seal(row[col]) for col in columns
                            if row[col] is not None and not crypto.is_encrypted(row[col])}
                    if todo:
                        sets = ", ".join(f"{col} = ?" for col in todo)
                        c.execute(f"UPDATE {table} SET {sets} WHERE {KEY_ROW[table]} = ?",
                                  (*todo.values(), row[KEY_ROW[table]]))

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_user(self, chat_id: int, b: BirthInput, now: float | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?,?,?)",
                (chat_id, *map(self._seal, (b.date_text, b.time_text, b.place_text, b.place_choice, b.fold)),
                 b.profile, self._seal(b.approx_for), int(now if now is not None else time.time())),
            )

    def get_user(self, chat_id: int) -> BirthInput | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        if r is None:
            return None
        fold = self._open(r["fold"])
        return BirthInput(self._open(r["date_text"]), self._open(r["time_text"]), self._open(r["place_text"]),
                          self._open(r["place_choice"]), None if fold is None else int(fold), r["profile"],
                          self._open(r["approx_for"]))

    def save_draft(self, chat_id: int, data: dict, now: float | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO drafts VALUES (?,?,?)",
                (chat_id, self._seal(json.dumps(data)), int(now if now is not None else time.time())),
            )

    def get_draft(self, chat_id: int, now: float | None = None) -> dict | None:
        """The draft, or None if there is none or it has expired (expired drafts are deleted)."""
        now = time.time() if now is None else now
        with self._conn() as c:
            r = c.execute("SELECT data, updated_at FROM drafts WHERE chat_id = ?", (chat_id,)).fetchone()
            if r is None:
                return None
            if now - r["updated_at"] > DRAFT_TTL_SECONDS:
                c.execute("DELETE FROM drafts WHERE chat_id = ?", (chat_id,))
                return None
        return json.loads(self._open(r["data"]))

    def delete_draft(self, chat_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM drafts WHERE chat_id = ?", (chat_id,))

    def purge_expired(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self._conn() as c:
            return c.execute("DELETE FROM drafts WHERE updated_at < ?", (int(now - DRAFT_TTL_SECONDS),)).rowcount

    def save_home(self, chat_id: int, place_text: str, place_id: str) -> None:
        """Set or change the living city; the morning-message setting is kept."""
        with self._conn() as c:
            c.execute(
                "INSERT INTO homes (chat_id, place_text, place_id) VALUES (?,?,?) "
                "ON CONFLICT(chat_id) DO UPDATE SET place_text = excluded.place_text, "
                "place_id = excluded.place_id, brief_last = NULL",
                (chat_id, self._seal(place_text), self._seal(place_id)),
            )

    def _home(self, r: sqlite3.Row) -> Home:
        return Home(self._open(r["place_text"]), self._open(r["place_id"]), r["brief_hour"], r["brief_last"])

    def get_home(self, chat_id: int) -> Home | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM homes WHERE chat_id = ?", (chat_id,)).fetchone()
        return self._home(r) if r else None

    def set_brief(self, chat_id: int, hour: int | None) -> None:
        """Turn the morning message on at a local hour, or off with None. Needs a home city."""
        with self._conn() as c:
            c.execute("UPDATE homes SET brief_hour = ?, brief_last = NULL WHERE chat_id = ?", (hour, chat_id))

    def mark_brief_sent(self, chat_id: int, local_date: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE homes SET brief_last = ? WHERE chat_id = ?", (local_date, chat_id))

    def briefs_enabled(self) -> list[tuple[int, Home]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM homes WHERE brief_hour IS NOT NULL").fetchall()
        return [(r["chat_id"], self._home(r)) for r in rows]

    def record_miss(self, topic: str) -> None:
        """Count one unanswered question under its sorted topic. Anything that is not a plain
        topic key (which could carry someone's words) is refused."""
        if not is_topic(topic):
            raise ValueError("record_miss takes a topic key like 'dasha:saturn', never free text")
        with self._conn() as c:
            c.execute(
                "INSERT INTO topic_misses VALUES (?, 1) ON CONFLICT(topic) DO UPDATE SET count = count + 1", (topic,)
            )

    def top_misses(self, limit: int = 20) -> list[tuple[str, int]]:
        with self._conn() as c:
            rows = c.execute("SELECT topic, count FROM topic_misses ORDER BY count DESC, topic LIMIT ?", (limit,))
            return [(r["topic"], r["count"]) for r in rows]

    def rekey(self, new_key: str) -> None:
        """Re-encrypt everything under a new key, atomically (all or nothing). The caller must then
        use the new key; keep a backup first."""
        new = crypto.Cipher(new_key)
        with self._conn() as c:
            for table, columns in SEALED.items():
                for row in c.execute(f"SELECT * FROM {table}").fetchall():
                    changed = {col: new.encrypt(self._cipher.decrypt(str(row[col])))
                               for col in columns if row[col] is not None}
                    if changed:
                        sets = ", ".join(f"{col} = ?" for col in changed)
                        c.execute(f"UPDATE {table} SET {sets} WHERE {KEY_ROW[table]} = ?",
                                  (*changed.values(), row[KEY_ROW[table]]))
            c.execute("UPDATE keycheck SET token = ? WHERE id = 1", (new.encrypt(CHECK_VALUE),))
        self._cipher = new

    def backup(self, out: str | os.PathLike) -> Path:
        """A consistent copy of the database. It holds only encrypted personal data, but the key is
        not in it: keep the key safe separately, because without it the copy cannot be read."""
        dest = Path(out)
        if dest.exists():
            raise FileExistsError(f"{dest} already exists; refusing to overwrite a backup")
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        src, dst = self._conn(), sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return dest

    def forget(self, chat_id: int) -> None:
        """Remove everything stored about a chat."""
        with self._conn() as c:
            for table in ("users", "drafts", "homes"):
                c.execute(f"DELETE FROM {table} WHERE chat_id = ?", (chat_id,))
