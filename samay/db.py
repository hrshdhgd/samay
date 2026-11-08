"""SQLite storage for users' birth data."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime

DB_PATH = os.environ.get("SAMAY_DB", "samay.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id    INTEGER PRIMARY KEY,
    birth_utc  TEXT NOT NULL,
    latitude   REAL NOT NULL,
    longitude  REAL NOT NULL,
    tz         TEXT NOT NULL,
    place      TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True)
class User:
    chat_id: int
    birth_utc: datetime
    latitude: float
    longitude: float
    tz: str
    place: str


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def save_user(u: User) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO users (chat_id, birth_utc, latitude, longitude, tz, place) VALUES (?,?,?,?,?,?)",
            (u.chat_id, u.birth_utc.isoformat(), u.latitude, u.longitude, u.tz, u.place),
        )


def get_user(chat_id: int) -> User | None:
    with _conn() as c:
        row = c.execute(
            "SELECT chat_id, birth_utc, latitude, longitude, tz, place FROM users WHERE chat_id=?", (chat_id,)
        ).fetchone()
    if not row:
        return None
    return User(row[0], datetime.fromisoformat(row[1]), row[2], row[3], row[4], row[5])


def delete_user(chat_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM users WHERE chat_id=?", (chat_id,))
