"""SQLite store for the bot: saved birth details and in-progress conversations.

Birth details are kept exactly as the user entered them and re-resolved on every read, so data
corrections apply automatically. Plaintext on disk until the encryption sub-project; do not
deploy before that lands.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

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
]


class Store:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path or os.environ.get("SAMAY_DB") or DATA_DIR / "samay.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
                c.executescript(script)
                c.execute(f"PRAGMA user_version = {i}")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_user(self, chat_id: int, b: BirthInput, now: float | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?,?,?)",
                (chat_id, b.date_text, b.time_text, b.place_text, b.place_choice, b.fold, b.profile,
                 b.approx_for, int(now if now is not None else time.time())),
            )

    def get_user(self, chat_id: int) -> BirthInput | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        if r is None:
            return None
        return BirthInput(r["date_text"], r["time_text"], r["place_text"], r["place_choice"], r["fold"],
                          r["profile"], r["approx_for"])

    def save_draft(self, chat_id: int, data: dict, now: float | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO drafts VALUES (?,?,?)",
                (chat_id, json.dumps(data), int(now if now is not None else time.time())),
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
        return json.loads(r["data"])

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
                (chat_id, place_text, place_id),
            )

    @staticmethod
    def _home(r: sqlite3.Row) -> Home:
        return Home(r["place_text"], r["place_id"], r["brief_hour"], r["brief_last"])

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

    def forget(self, chat_id: int) -> None:
        """Remove everything stored about a chat."""
        with self._conn() as c:
            for table in ("users", "drafts", "homes"):
                c.execute(f"DELETE FROM {table} WHERE chat_id = ?", (chat_id,))
