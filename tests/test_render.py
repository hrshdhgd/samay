from datetime import UTC, datetime

import pytest

from samay import service
from samay.engine.ephemeris import GRAHAS
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput, NeedsDisambiguation
from samay.render.text import (
    DISCLAIMER,
    UNVALIDATED,
    render_chart,
    render_dasha,
    render_options,
    render_today,
)

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")


def _report(date_text="1990-08-15", time_text="14:30"):
    return service.natal_report(service.resolve_birth(BirthInput(date_text, time_text, "Pune")))


def test_chart_text_has_everything():
    text = render_chart(_report())
    assert text.startswith("Lagna: ")
    for g in GRAHAS:
        assert g.title() in text
    for needle in ("UTC+05:30", "confidence: tzdata", "parashari-lahiri", UNVALIDATED, DISCLAIMER):
        assert needle in text


def test_warning_shown_for_1952_pune():
    assert "Bombay Time" in render_chart(_report("1952-08-05", "06:00"))


def test_dasha_and_today():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert "← now" in render_dasha(_report(), now)
    birth = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    text = render_today(service.today_report(birth, now))
    assert "Transiting Saturn" in text and "mahadasha" in text


def test_options():
    d = service.resolve_birth(BirthInput("2021-11-07", "01:30", "New York City"))
    assert isinstance(d, NeedsDisambiguation)
    assert render_options(d)[0].startswith("first occurrence")
