"""Whose chart an answer is about: the user's own, or another person's (a child, a spouse, a parent).

Answers are worded from this ("your 7th house" or "Maya's 7th house"), so one set of code serves both.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_NAME = 40
MAX_RELATION = 30


def clean(text: str, limit: int) -> str:
    """A name or relation that is safe to show and store: single line, no control characters, bounded."""
    kept = "".join(c for c in str(text) if c.isprintable() and c not in "\r\n\t")
    return " ".join(kept.split())[:limit].strip()


@dataclass(frozen=True)
class Subject:
    name: str | None = None  # None means the user themself
    relation: str | None = None  # "daughter", "husband", ...
    minor: bool = False  # under 18: the classical texts describe adult life, so answers say so

    @property
    def is_self(self) -> bool:
        return self.name is None

    @property
    def your(self) -> str:
        return "your" if self.is_self else f"{self.name}'s"

    @property
    def Your(self) -> str:
        return "Your" if self.is_self else f"{self.name}'s"

    @property
    def you_are(self) -> str:
        return "you are" if self.is_self else f"{self.name} is"

    @property
    def heading(self) -> str:
        """A line that says whom an answer is about; empty for the user's own."""
        if self.is_self:
            return ""
        return f"👤 {self.name}" + (f" ({self.relation})" if self.relation else "")


SELF = Subject()
