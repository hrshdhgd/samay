"""Sourced knowledge entries: plain-English paraphrases of classical verses, each with a citation.

An entry is only ever shown to a user once it has been checked (see LEVELS). A Sanskrit verse is
only shown if its own text was checked against a second copy: a mistyped verse under a citation
is worse than none. Entries live in data/entries/*.yaml and are written from public-domain
sources only (see data/entries/README.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from .paths import DATA_DIR

ENTRIES_DIR = DATA_DIR / "entries"
LEVELS = ("unchecked", "translation-checked", "sanskrit-checked")
SERVABLE_LEVELS = frozenset(LEVELS[1:])
TOPIC = re.compile(r"[a-z0-9_]+(:[a-z0-9_]+){0,3}")  # e.g. "dasha:saturn", "transit:saturn:11"
_REQUIRED = {"id", "topic", "system", "english", "citation", "verification"}
# "any": not tied to a calculation system (e.g. the nature of a planet). Otherwise the system the
# entry describes, e.g. "vimshottari"; such an entry only answers questions about that system.
ANY_SYSTEM = "any"
SYSTEM = re.compile(r"[a-z0-9-]+")


@dataclass(frozen=True)
class Verse:
    devanagari: str
    roman: str
    text_checked: bool  # the verse text was compared with a second copy of the text (mechanically)
    proofread: bool = False  # a Sanskrit reader has read it; False means typed text nobody fluent has proofread
    source: str | None = None  # where the typed text comes from


@dataclass(frozen=True)
class Verification:
    level: str
    checked_by: str | None = None
    checked_on: date | None = None
    against: str | None = None  # the public-domain translation, or the edition read, used for the check


@dataclass(frozen=True)
class Entry:
    id: str
    topic: str
    system: str
    english: str
    citation: dict  # text, chapter, verse, edition
    verification: Verification
    verse: Verse | None = None

    @property
    def servable(self) -> bool:
        return self.verification.level in SERVABLE_LEVELS

    @property
    def shows_verse(self) -> bool:
        return self.servable and self.verse is not None and self.verse.text_checked

    def citation_text(self) -> str:
        c = self.citation
        return f"{c['text']} {c['chapter']}.{c['verse']} ({self.verification.level})"


def is_topic(text: str) -> bool:
    return bool(TOPIC.fullmatch(text)) and len(text) <= 64


def _parse(raw: dict, where: str) -> Entry:
    missing = _REQUIRED - raw.keys()
    if missing:
        raise ValueError(f"{where}: missing {sorted(missing)}")
    if not is_topic(raw["topic"]):
        raise ValueError(f"{where}: topic {raw['topic']!r} must look like 'dasha:saturn'")
    if not SYSTEM.fullmatch(str(raw["system"])):
        raise ValueError(f"{where}: system must be 'any' or an id like 'vimshottari'")
    if not {"text", "chapter", "verse", "edition"} <= raw["citation"].keys():
        raise ValueError(f"{where}: citation needs text, chapter, verse and edition")
    v = raw["verification"]
    if v.get("level") not in LEVELS:
        raise ValueError(f"{where}: verification.level must be one of {LEVELS}")
    if v["level"] in SERVABLE_LEVELS and not (v.get("checked_by") and v.get("checked_on")):
        raise ValueError(f"{where}: a {v['level']} entry needs checked_by and checked_on")
    if v["level"] == "translation-checked" and not v.get("against"):
        raise ValueError(f"{where}: a translation-checked entry must name the translation it was checked against")
    verse = None
    if raw.get("verse"):
        rv = raw["verse"]
        if not (rv.get("devanagari") and rv.get("roman")):
            raise ValueError(f"{where}: a verse needs both devanagari and roman text")
        verse = Verse(rv["devanagari"], rv["roman"], bool(rv.get("text_checked")), bool(rv.get("proofread")),
                      rv.get("source"))
    return Entry(
        id=raw["id"], topic=raw["topic"], system=raw["system"], english=raw["english"].strip(), citation=dict(raw["citation"]),
        verification=Verification(v["level"], v.get("checked_by"), v.get("checked_on"), v.get("against")),
        verse=verse,
    )


@lru_cache(maxsize=4)
def load_entries(directory: Path = ENTRIES_DIR) -> tuple[Entry, ...]:
    entries = []
    for path in sorted(directory.glob("*.yaml")):
        for i, raw in enumerate(yaml.safe_load(path.read_text(encoding="utf-8")) or []):
            entries.append(_parse(raw, f"{path.name}[{i}]"))
    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate entry ids")
    return tuple(entries)


def answers_for(topic: str, systems: frozenset[str] = frozenset(), directory: Path | None = None) -> list[Entry]:
    """Entries that may be shown for a topic: checked ones only, most thoroughly checked first.
    An entry tied to a calculation system is only returned when that system is in `systems`
    (the systems the user's chart was computed with), so it never explains a different system."""
    allowed = {ANY_SYSTEM, *systems}
    directory = directory or ENTRIES_DIR  # looked up now, not when the module loads, so it can be swapped
    found = [e for e in load_entries(directory) if e.topic == topic and e.servable and e.system in allowed]
    # Most thoroughly checked first, then in the order the source gives them (file order).
    return sorted(found, key=lambda e: -LEVELS.index(e.verification.level))
