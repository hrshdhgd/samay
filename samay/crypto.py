"""Encryption of personal data at rest (Fernet: AES-128-CBC with HMAC-SHA256, authenticated).

The key never lives in the database. It comes from the SAMAY_DB_KEY environment variable (the
server) or, for local development only, from a key file that is created on first use with
owner-only permissions. Values are stored as "enc1:<token>"; anything without the prefix is
legacy plaintext and is upgraded when the store opens.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .engine.errors import SamayError
from .engine.paths import DATA_DIR

log = logging.getLogger("samay")
PREFIX = "enc1:"
KEY_ENV = "SAMAY_DB_KEY"
KEY_FILE = DATA_DIR / "samay.key"


class StoreKeyError(SamayError):
    """The database key is missing, malformed, or does not match the database."""


def generate_key() -> str:
    return Fernet.generate_key().decode()


def resolve_key(env: dict | None = None, key_file: Path | None = None) -> str:
    """The key from SAMAY_DB_KEY, else from the key file (created with mode 0600 if absent)."""
    env = os.environ if env is None else env
    key_file = key_file or KEY_FILE
    key = env.get(KEY_ENV, "").strip()
    if key:
        return key
    if key_file.is_file():
        return key_file.read_text().strip()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = generate_key()
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    log.warning("created a local database key at %s; on a server set %s instead", key_file, KEY_ENV)
    return key


class Cipher:
    def __init__(self, key: str):
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError):
            raise StoreKeyError(f"{KEY_ENV} is not a valid key; make one with: uv run samay keygen") from None

    def encrypt(self, value: str) -> str:
        return PREFIX + self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        """The plaintext. A value without the prefix is legacy plaintext and is returned as it is."""
        if not value.startswith(PREFIX):
            return value
        try:
            return self._fernet.decrypt(value[len(PREFIX):].encode()).decode()
        except InvalidToken:
            raise StoreKeyError("the database key does not match this database") from None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)
