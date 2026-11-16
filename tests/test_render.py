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


def _family(date_text, time_text, place):
    report = service.natal_report(service.resolve_birth(BirthInput(date_text, time_text, place)))
    return report, render_chart(report, technical=False)


def test_family_footer_is_short_and_free_of_technical_noise():
    report, text = _family("1990-08-15", "14:30", "Pune")
    for noise in (UNVALIDATED, "samay dev", "profile parashari", "tzdata", "confidence:", "UTC", "ayanamsa"):
        assert noise not in text, noise
    assert text.count(DISCLAIMER) == 1
    assert text.splitlines()[-1] == f"ref {report.stamp.code()}"
    assert "Born 15 Aug 1990, 14:30 · Pune" in text
    assert "⚠" not in text  # a modern Indian birth needs no caution


def test_family_footer_keeps_the_cautions_that_matter():
    assert "Bombay Time" in _family("1952-08-05", "06:00", "Pune")[1]
    assert "double-check the birth time" in _family("1960-06-01", "12:00", "Chicago")[1]
    assert "double-check" not in _family("1990-08-15", "14:30", "Pune")[1]


def test_family_chart_notes_unverified_yoga_sources_only_when_yogas_are_shown():
    for date_text, time_text in (("1990-08-15", "14:30"), ("1952-08-05", "06:00"), ("1985-06-15", "08:30")):
        report, text = _family(date_text, time_text, "Pune")
        has_unverified = any(not r.source.get("verified") for r in report.yogas)
        assert ("still being checked" in text) == has_unverified


def test_technical_output_is_unchanged_for_the_cli():
    text = render_chart(_report())
    assert UNVALIDATED in text and "samay dev" in text and "Time standard:" in text


def test_reference_code_is_stable_and_changes_with_the_data():
    from dataclasses import replace

    stamp = _report().stamp
    assert len(stamp.code()) == 8 and stamp.code() == _report().stamp.code()
    assert replace(stamp, tzdata_version="1999.1").code() != stamp.code()


def test_clock12_rounds_to_the_nearest_minute_and_handles_noon_and_midnight():
    from samay.render.text import clock12

    day = datetime(2026, 11, 9, tzinfo=UTC)
    assert clock12(day.replace(hour=8, minute=0, second=22)) == "8:00 am"
    assert clock12(day.replace(hour=9, minute=21, second=50)) == "9:22 am"
    assert clock12(day.replace(hour=12, minute=5)) == "12:05 pm"
    assert clock12(day.replace(hour=0, minute=40)) == "12:40 am"
    assert clock12(day.replace(hour=23, minute=59, second=45)) == "12:00 am"


def test_rahu_kaala_line_and_polar_message():
    from datetime import date

    from samay.engine import daylight
    from samay.render.text import render_rahu_kaala

    rahu = daylight.rahu_kaala(28.6139, 77.2090, "Asia/Kolkata", date(2026, 11, 9))
    assert render_rahu_kaala(rahu, "New Delhi") == "⚠ Rahu Kaala today: 8:00 am – 9:22 am (New Delhi)"
    assert "does not both rise and set" in render_rahu_kaala(None, "Tromsø")


def test_brief_has_date_rahu_kaala_and_dasha_dates_but_no_meanings():
    from datetime import date

    from samay.engine import daylight
    from samay.render.text import render_brief

    rahu = daylight.rahu_kaala(18.5196, 73.8553, "Asia/Kolkata", date(2026, 11, 9))
    dasha = service.today_report(service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune")),
                                 datetime(2026, 11, 9, tzinfo=UTC)).current_dasha
    text = render_brief(datetime(2026, 11, 9, 7, 0), rahu, "Pune", dasha)
    assert text.splitlines()[0] == "🌅 Good morning! Today is Monday, 09 November 2026."
    assert "Rahu Kaala today:" in text and "(Pune)" in text
    assert "Jupiter chapter (mahadasha) until" in text and "Venus sub-chapter (antardasha) until" in text
    assert len(render_brief(datetime(2026, 11, 9, 7, 0), rahu, "Pune", None).splitlines()) == 2


def test_today_can_carry_extra_lines_before_the_footer():
    from samay.render.text import render_today

    birth = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    report = service.today_report(birth, datetime(2026, 11, 9, tzinfo=UTC))
    lines = render_today(report, technical=False, extras=("⚠ Rahu Kaala today: X",)).splitlines()
    assert "⚠ Rahu Kaala today: X" in lines and lines.index("⚠ Rahu Kaala today: X") < len(lines) - 3


def test_ordinals():
    from samay.render.text import ordinal

    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12)] == ["1st", "2nd", "3rd", "4th", "11th", "12th"]


def _today(now=datetime(2026, 11, 9, tzinfo=UTC)):
    birth = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    return service.today_report(birth, now)


def test_chat_today_is_short_and_plain_with_no_planet_positions():
    from samay.render.text import render_today

    text = render_today(_today(), technical=False, extras=("⚠ Rahu Kaala today: X",))
    lines = text.splitlines()
    assert lines[0] == "🌙 Today, Monday 09 November 2026"
    assert "You are in a Jupiter period of life that runs until Feb 2033, and within it a Venus phase until 02 Sep 2027." in text
    assert "⚠ Rahu Kaala today: X" in lines and "Technical details" not in text and "sign from your Moon" not in text and "Transiting" not in text


def test_plain_today_has_no_meanings_only_computed_facts():
    from samay.render.text import plain_today

    text = " ".join(plain_today(_today())).lower()
    for meaning_word in ("auspicious", "good for", "bad for", "indicates", "brings", "sade sati", "will "):
        assert meaning_word not in text


def test_cli_today_is_unchanged():
    from samay.render.text import render_today

    text = render_today(_today())
    assert text.startswith("Today (09 Nov 2026).") and "Technical details" not in text


def test_chat_dasha_is_explained_with_lengths_dates_and_the_current_sub_chapters():
    now = datetime(2026, 11, 9, tzinfo=UTC)
    text = render_dasha(_report(), now, technical=False)
    assert text.startswith("Your life chapters (dashas)") and "120 years" in text
    rows = [line for line in text.splitlines() if " · " in line and "years" in line]
    assert len(rows) == 9 and sum(1 for r in rows if "← now" in r) == 1
    assert next(r for r in rows if "← now" in r).startswith("Jupiter · 16 years · ")
    assert rows[0].split(" · ")[2].startswith("birth –")  # the first chapter began before birth
    assert "Rahu and Ketu are not planets you can see" in text
    assert "Sub-chapters inside your Jupiter chapter:" in text
    assert sum(1 for line in text.splitlines() if line.endswith("← now")) == 2  # chapter + sub-chapter


def test_cli_dasha_is_unchanged():
    assert render_dasha(_report(), datetime(2026, 11, 9, tzinfo=UTC)).startswith("Vimshottari mahadashas:")


def test_a_short_text_is_one_message_and_a_long_one_is_split_without_losing_a_word():
    from samay.render.text import split_message
    assert split_message("hello") == ["hello"]
    paragraphs = [f"paragraph {i} " + "word " * 120 for i in range(20)]
    text = "\n\n".join(paragraphs)
    parts = split_message(text, limit=1000)
    assert len(parts) > 2 and all(len(p) <= 1000 for p in parts)
    assert "\n\n".join(parts).split() == text.split()  # nothing dropped or reordered
    assert all(p.startswith("paragraph") for p in parts)  # cut at paragraph boundaries here


def test_a_paragraph_longer_than_the_limit_is_cut_at_lines_and_then_at_words():
    from samay.render.text import split_message
    lines = "\n".join(f"line {i} " + "x" * 80 for i in range(30))
    parts = split_message(lines, limit=500)
    assert all(len(p) <= 500 for p in parts) and "\n".join(parts).split() == lines.split()
    one_long_line = "word " * 400
    pieces = split_message(one_long_line, limit=300)
    assert all(len(p) <= 300 for p in pieces) and " ".join(pieces).split() == one_long_line.split()


def test_a_word_longer_than_the_limit_is_cut_hard_rather_than_looping():
    from samay.render.text import split_message
    assert all(len(p) <= 100 for p in split_message("y" * 250, limit=100))


def test_today_gives_the_books_meaning_only_when_it_is_kind(monkeypatch):
    import dataclasses

    from samay.engine import antardasha
    from samay.render import text as T
    rules = dataclasses.replace(antardasha.load_rules(), level="translation-checked", checked_by="test")
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: rules)
    kind = [k for k, (t, _) in rules.effects.items() if not any(w in t.lower() for w in T.HARSH_WORDS)]
    hard = [k for k, (t, _) in rules.effects.items() if any(w in t.lower() for w in T.HARSH_WORDS)]
    assert kind and hard
    assert "is about" in T._gentle_phase(*kind[0]) and "mixed phase" in T._gentle_phase(*hard[0]) and rules.effects[hard[0]][0] not in T._gentle_phase(*hard[0])
