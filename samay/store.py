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
from pathlib import Path

from .models import BirthInput

DRAFT_TTL_SECONDS = 30 * 60

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
]


class Store:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path or os.environ.get("SAMAY_DB", "samay.db"))
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

    def forget(self, chat_id: int) -> None:
        """Remove everything stored about a chat."""
        with self._conn() as c:
            c.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
            c.execute("DELETE FROM drafts WHERE chat_id = ?", (chat_id,))
