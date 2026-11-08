"""Typed errors. Front ends map each one to a single user-facing message."""
from __future__ import annotations


class SamayError(Exception):
    """Base class for errors a user can act on."""


class InvalidInput(SamayError):
    pass


class PlaceNotFound(SamayError):
    pass


class NonexistentTime(SamayError):
    """The local clock never showed this time (skipped by a DST change)."""


class OutOfEphemerisRange(SamayError):
    pass


class EphemerisMissing(SamayError):
    pass


class UnknownProfile(SamayError):
    pass


class UnsupportedLatitude(SamayError):
    pass
