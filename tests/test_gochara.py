"""Phaladeepika chapter 26 transits: the rules file, the stays, vedha, the period report, and how it is shown."""
import dataclasses
import itertools
from datetime import UTC, datetime, timedelta

import pytest
import yaml

from samay import qa, service
from samay.engine import ephemeris, gochara
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render import prompts
from samay.render.text import render_answer
from samay.subject import Subject

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
NOW = datetime(2026, 11, 12, 6, tzinfo=UTC)
RULES = gochara.load_rules()
CHECKED = dataclasses.replace(RULES, level="translation-checked", checked_by="test")


# --- the rules file ------------------------------------------------------------------------------------------------


def test_the_rules_file_has_every_house_for_every_planet_the_text_covers_and_no_ketu():
    assert set(RULES.effects) == {"sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu"}
    assert all(set(h) == set(range(1, 13)) for h in RULES.effects.values())
    assert "ketu" not in RULES.favourable  # the author gives Ketu no results


def test_the_good_houses_are_verse_2s():
    assert RULES.favourable["sun"] == {3, 6, 10, 11}
    assert RULES.favourable["jupiter"] == {2, 5, 7, 9, 11}
    assert RULES.favourable["saturn"] == {3, 6, 11}
    assert RULES.favourable["venus"] == {1, 2, 3, 4, 5, 8, 9, 11, 12}


def test_vedha_follows_verses_3_to_7_and_leaves_out_what_the_text_does_not_say_clearly():
    assert RULES.vedha["jupiter"].pairs == {2: 12, 11: 8, 9: 10, 5: 4, 7: 3}
    assert RULES.vedha["sun"].exempt == {"saturn"} and RULES.vedha["moon"].exempt == {"mercury"}
    assert 8 not in RULES.vedha["mercury"].pairs  # the translation drops it
    assert "venus" not in RULES.vedha  # verse 8's lists do not line up


def test_the_shipped_rules_are_unchecked_until_a_person_checks_them():
    assert RULES.level == "unchecked" and not RULES.servable


def _write(tmp_path, change):
    raw = yaml.safe_load(gochara.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize("change", [
    lambda r: r["effects"]["sun"]["houses"].pop(5),
    lambda r: r["effects"].update(pluto={"verse": "1", "houses": {}}),
    lambda r: r["vedha"]["jupiter"]["pairs"].update({9: 9}),
    lambda r: r["vedha"]["jupiter"]["pairs"].update({1: 7}),  # the 1st is not a good house for Jupiter
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
    lambda r: r["favourable"]["sun"].append(13),
])
def test_a_malformed_rules_file_is_rejected(tmp_path, change):
    with pytest.raises(ValueError):
        gochara.load_rules(_write(tmp_path, change))


def test_a_checker_can_hide_a_row(tmp_path):
    def hide(raw):
        raw["verification"] = {"level": "translation-checked", "checked_by": "h2", "checked_on": "2026-11-12"}
        raw["effects"]["rahu"]["houses"][1] = {"text": raw["effects"]["rahu"]["houses"][1], "hidden": True}
    rules = gochara.load_rules(_write(tmp_path, hide))
    times, track = _synthetic({"rahu": [0, 0]})
    (stay,) = gochara.stays(times, track, 0, ("rahu",), rules)
    assert stay.house == 1 and stay.effect is None


# --- stays and vedha, on a made-up sky ------------------------------------------------------------------------------


def _synthetic(signs: dict[str, list[int]]):
    """A track where each planet sits mid-sign in the given signs at hourly moments; everyone else in Aries."""
    n = len(next(iter(signs.values())))
    times = [NOW + timedelta(hours=k) for k in range(n)]
    track = {g: [15.0] * n for g in gochara.GRAHAS}
    for g, seq in signs.items():
        track[g] = [s * 30 + 15.0 for s in seq]
    return times, track


def test_stays_split_at_sign_changes_and_count_houses_from_the_moon_sign():
    times, track = _synthetic({"sun": [2, 2, 3, 3, 3]})
    first, second = gochara.stays(times, track, moon_sign=0, planets=("sun",))
    assert (first.house, first.start, first.end) == (3, None, times[2])
    assert (second.house, second.start, second.end) == (4, times[2], None)


def test_effects_are_only_given_from_a_checked_file():
    times, track = _synthetic({"jupiter": [8, 8]})  # Sagittarius: 9th from an Aries Moon
    (unchecked,) = gochara.stays(times, track, 0, ("jupiter",), RULES)
    (checked,) = gochara.stays(times, track, 0, ("jupiter",), CHECKED)
    assert unchecked.favourable and unchecked.effect is None
    assert checked.effect == RULES.effects["jupiter"][9] and checked.verse == "18-20"


def test_a_planet_in_the_vedha_house_blocks_a_good_result_but_an_exempt_one_does_not():
    # Sun in the 11th from an Aries Moon (Aquarius); its vedha house is the 5th (Leo).
    times, track = _synthetic({"sun": [10, 10], "mars": [4, 4], "saturn": [4, 4], "moon": [0, 0]})
    (stay,) = gochara.stays(times, track, 0, ("sun",), CHECKED)
    assert stay.vedha_house == 5 and stay.blocked_by == ("mars",)  # Saturn does not obstruct the Sun


def test_vedha_is_not_checked_when_asked_not_to_and_ketu_gets_no_reading():
    times, track = _synthetic({"sun": [10, 10], "mars": [4, 4]})
    (stay,) = gochara.stays(times, track, 0, ("sun",), CHECKED, check_vedha=False)
    assert stay.vedha_house == 5 and stay.blocked_by == ()
    (ketu,) = gochara.stays(times, track, 0, ("ketu",), CHECKED)
    assert ketu.favourable is None and ketu.effect is None


# --- the sky over a period ------------------------------------------------------------------------------------------


@needs_kernel
def test_the_vectorised_track_matches_a_single_chart():
    moments = [NOW, NOW + timedelta(days=40), datetime(2031, 3, 1, tzinfo=UTC)]
    track = ephemeris.sidereal_track(moments)
    for i, t in enumerate(moments):
        chart = ephemeris.compute_chart(t, 18.5, 73.9)
        for g, p in chart.planets.items():
            assert track[g][i] == pytest.approx(p.longitude, abs=1e-9)


def test_the_track_refuses_naive_times():
    with pytest.raises(ValueError):
        ephemeris.sidereal_track([datetime(2026, 1, 1)])


def _birth():
    return service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))


@needs_kernel
def test_the_sun_enters_scorpio_on_vrishchika_sankranti_2026():
    report = service.outlook_report(_birth(), NOW, "week")
    sun = [s for s in report.stays if s.planet == "sun"]
    assert [s.sign for s in sun] == [6, 7]  # Libra, then Scorpio
    assert sun[1].start.date() == datetime(2026, 11, 16).date()


@needs_kernel
@pytest.mark.parametrize("span", list(service.OUTLOOK_SPANS))
def test_each_span_covers_its_length_and_its_stays_join_up(span):
    report = service.outlook_report(_birth(), NOW, span)
    assert report.end - report.start == service.OUTLOOK_SPANS[span][0]
    planets = service.OUTLOOK_SPANS[span][2]
    assert {s.planet for s in report.stays} == set(planets)
    for g in planets:
        mine = [s for s in report.stays if s.planet == g]
        assert mine[0].start is None and mine[-1].end is None
        assert all(a.end == b.start for a, b in itertools.pairwise(mine))
    assert ("moon" in planets) == (span in ("week", "fortnight"))


@needs_kernel
def test_sub_chapters_beginning_inside_the_period_are_listed():
    report = service.outlook_report(_birth(), NOW, "years")
    assert report.dasha_at_start[0].lord == "rahu" and report.dasha_at_start[1].lord == "saturn"
    assert [(lord, a.lord) for lord, a in report.dasha_changes] == [("rahu", "mercury")]
    assert all(report.start < a.start < report.end for _, a in report.dasha_changes)


# --- routing, answers and what is shown -----------------------------------------------------------------------------


@pytest.mark.parametrize(("question", "topic"), [
    ("What does my upcoming week look like", "future:week"),
    ("how will the next fortnight go", "future:fortnight"),
    ("what is this month like for me", "future:month"),
    ("how is this year", "future:year"),
    ("what about the next few years", "future:years"),
    ("am I going to be lucky next year", "future:year"),
    ("will I get married this year", "life:marriage"),
    ("what will Saturn do this year", "planet:saturn"),
])
def test_the_offline_rules_find_the_period(question, topic):
    assert qa.sort_question(question) == topic


def test_the_router_is_told_about_every_period():
    for topic in qa.OUTLOOK_TOPICS:
        assert topic in qa.TOPICS and topic in qa.MODEL_SYSTEM


def test_without_a_birth_the_period_answer_asks_for_one():
    answer = qa.answer_topic("future:week", None, NOW)
    assert answer.outlook is None and render_answer(answer, birth_known=False) == prompts.NEED_BIRTH_FOR_FUTURE


@needs_kernel
def test_unchecked_rules_show_positions_only():
    text = render_answer(qa.answer_topic("future:week", _birth(), NOW))
    assert "🔮 Your week ahead" in text and "Sagittarius (Dhanu)" in text and prompts.OUTLOOK_UNCHECKED in text
    assert not any(effect in text for houses in RULES.effects.values() for effect in houses.values())
    assert "✓" not in text and "Source:" not in text


@needs_kernel
def test_checked_rules_show_the_texts_results_marks_and_source(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    answer = qa.answer_topic("future:week", _birth(), NOW, tz="America/Chicago")
    text = render_answer(answer)
    assert RULES.effects["jupiter"][9] in text and "✓" in text and prompts.OUTLOOK_KEY in text
    assert "Source: Phaladeepika 26.2–8" in text and "· checked" in text
    assert "⛔ blocked by" in text  # Jupiter in the 9th with Venus in the 10th that week
    full = render_answer(answer, "full")
    assert prompts.OUTLOOK_NOT_APPLIED in full and "G. S. Kapoor" in full


@needs_kernel
def test_dates_are_shown_in_the_timezone_asked_for(monkeypatch):
    india = render_answer(qa.answer_topic("future:week", _birth(), NOW))
    chicago = render_answer(qa.answer_topic("future:week", _birth(), NOW, tz="America/Chicago"))
    assert "Mon 16 Nov 9 am" in chicago and "Mon 16 Nov 9 am" not in india  # the Sun's ingress


@needs_kernel
def test_a_result_is_not_repeated_when_a_planet_turns_back_into_a_house(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW))
    jupiter = next(line for line in text.splitlines() if line.startswith("♃"))
    assert jupiter.count(RULES.effects["jupiter"][9]) == 1 and jupiter.count("9th ✓") > 1


@needs_kernel
@pytest.mark.parametrize("born", [("1989-08-14", "12:00", "Mumbai, India"), ("1952-08-15", "06:30", "Pune"),
                                  ("2015-03-14", "06:30", "Pune")])
def test_every_view_fits_in_one_telegram_message(monkeypatch, born):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    birth = service.resolve_birth(BirthInput(*born))
    for topic in qa.OUTLOOK_TOPICS:
        answer = qa.answer_topic(topic, birth, NOW)
        for view in ("compact", "full"):
            assert len(render_answer(answer, view)) < 4096, (topic, view)


@needs_kernel
def test_another_persons_period_is_worded_for_them_and_the_ai_gets_the_facts(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    maya = Subject("Maya", "daughter", minor=True)
    answer = qa.answer_topic("future:month", _birth(), NOW, subject=maya)
    text = render_answer(answer)
    assert "🔮 Maya's month ahead" in text and "Maya's Moon sign" in text and prompts.MINOR_NOTE in text
    prompt = qa._ai_prompt("how is her month?", answer)
    assert "Phaladeepika chapter 26" in prompt and RULES.effects["jupiter"][9] in prompt
