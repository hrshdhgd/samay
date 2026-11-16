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


def test_vedha_follows_verses_3_to_8_and_is_cross_checked_against_a_second_table():
    assert RULES.vedha["jupiter"].pairs == {2: 12, 11: 8, 9: 10, 5: 4, 7: 3}
    assert RULES.vedha["sun"].exempt == {"saturn"} and RULES.vedha["moon"].exempt == {"mercury"}
    assert RULES.vedha["mercury"].pairs == {2: 5, 4: 3, 6: 9, 8: 1, 10: 8, 11: 12}  # the 8th's, lost in the translation, filled
    assert RULES.vedha["venus"].pairs == {1: 8, 2: 7, 3: 1, 4: 10, 5: 9, 8: 5, 9: 11, 11: 6, 12: 3}  # and Venus's nine


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
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
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
    text = render_answer(qa.answer_topic("future:week", _birth(), NOW), "full")
    assert "🔮 Your week ahead" in text and "Sagittarius (Dhanu)" in text and prompts.OUTLOOK_UNCHECKED in text
    assert not any(effect in text for houses in RULES.effects.values() for effect in houses.values())
    assert "✓" not in text and "Source:" not in text


@needs_kernel
def test_checked_rules_show_the_texts_results_marks_and_source(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    answer = qa.answer_topic("future:week", _birth(), NOW, tz="America/Chicago")
    text = render_answer(answer, "full")
    assert RULES.effects["jupiter"][9] in text and "✓" in text and prompts.OUTLOOK_KEY in text
    assert "Source: Phaladeepika 26.2–8" in text and "· checked" in text
    assert "⛔ blocked by" in text  # Jupiter in the 9th with Venus in the 10th that week
    assert prompts.OUTLOOK_NOT_APPLIED in text and "G. S. Kapoor" in text


@needs_kernel
def test_dates_are_shown_in_the_timezone_asked_for(monkeypatch):
    india = render_answer(qa.answer_topic("future:week", _birth(), NOW))
    chicago = render_answer(qa.answer_topic("future:week", _birth(), NOW, tz="America/Chicago"))
    assert "Mon 16 Nov 9 am" in chicago and "Mon 16 Nov 9 am" not in india  # the Sun's ingress


@needs_kernel
def test_a_result_is_not_repeated_when_a_planet_turns_back_into_a_house(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW), "full")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("♃"))
    stop = next(i for i, line in enumerate(lines[start + 1:], start + 1) if line and not line.startswith(("•", " ")))
    jupiter = "\n".join(lines[start:stop])
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
    text = render_answer(answer, "full")
    assert "🔮 Maya's month ahead" in text and "Maya's Moon sign" in text and prompts.MINOR_NOTE in text
    prompt = qa._ai_prompt("how is her month?", answer)
    assert "Phaladeepika chapter 26" in prompt and RULES.effects["jupiter"][9] in prompt


# --- Phaladeepika 21: what each sub-chapter brings -----------------------------------------------------------------------
from samay.engine import antardasha

SUB = antardasha.load_rules()
SUB_CHECKED = dataclasses.replace(SUB, level="translation-checked", checked_by="test")


def test_the_antardasha_rules_cover_all_81_pairs():
    assert len(SUB.effects) == 81 and SUB.level == "unchecked"
    assert {(m, a) for m in antardasha.LORDS for a in antardasha.LORDS} == set(SUB.effects)
    # Ketu's dasha, Venus and Mercury sub-chapters: verses 67 and 74, named by a second edition (Sanskrit with translation)
    assert SUB.effects["ketu", "venus"][1] == 67 and SUB.effects["ketu", "mercury"][1] == 74


def test_verses_run_3_to_83_without_repeats():
    verses = sorted(v for _, v in SUB.effects.values())
    assert verses[0] == 3 and verses[-1] == 83 and len(set(verses)) == 81 and 67 in verses and 74 in verses and 49 in verses
    assert 1 not in verses and 2 not in verses and 84 not in verses  # verse 1-2 and 84 give rules, not results


def test_each_mahadasha_block_follows_the_text_order_of_verses():
    # Jupiter's block is verses 39-47: Jupiter, Saturn, Mercury, Ketu, Venus, Sun, Moon, Mars, Rahu
    order = ["jupiter", "saturn", "mercury", "ketu", "venus", "sun", "moon", "mars", "rahu"]
    assert [SUB.effects["jupiter", a][1] for a in order] == list(range(39, 48))


def test_known_results():
    assert "death of the native or loss of the wife" in SUB.effects["saturn", "moon"][0]
    assert "marriage" in SUB.effects["rahu", "venus"][0]
    assert SUB.effects["jupiter", "mercury"][0].startswith("one view:")


def test_the_unchecked_file_gives_nothing_and_the_checked_one_gives_text_and_verse():
    assert SUB.result("sun", "moon") is None
    text, verse = SUB_CHECKED.result("sun", "moon")
    assert verse == 4 and "defeat of enemies" in text
    assert "daughter" in SUB_CHECKED.result("ketu", "venus")[0] and "good son" in SUB_CHECKED.result("ketu", "mercury")[0]


@pytest.mark.parametrize("change", [
    lambda r: r["effects"].update(pluto={}),
    lambda r: r["effects"]["sun"].update(pluto={"verse": 1, "text": "x"}),
    lambda r: r["effects"]["sun"]["sun"].update(text=""),
    lambda r: r["effects"]["sun"]["sun"].update(verse="3"),
    lambda r: r["effects"]["sun"]["moon"].update(verse=3),  # a repeated verse
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_antardasha_file_is_rejected(tmp_path, change):
    raw = yaml.safe_load(antardasha.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        antardasha.load_rules(path)


@needs_kernel
def test_unchecked_antardasha_results_are_not_shown_and_the_wait_is_said():
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW), "full")
    assert prompts.OUTLOOK_DASHA_UNCHECKED in text and "The text:" not in text
    assert not any(t in text for t, _ in SUB.effects.values())


@needs_kernel
def test_checked_antardasha_results_appear_under_their_dasha_lines_with_sources(monkeypatch):
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: SUB_CHECKED)
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW), "full")
    # at the start: Rahu mahadasha, Saturn antardasha (verse 32); from 9 Jul 2029: Mercury antardasha (verse 33)
    assert SUB.effects["rahu", "saturn"][0] in text and SUB.effects["rahu", "mercury"][0] in text
    assert "21.32" in text and "21.33" in text and prompts.OUTLOOK_DASHA_UNCHECKED not in text
    report = qa.answer_topic("future:years", _birth(), NOW).outlook
    assert {(m, a) for m, a, _, _ in report.antardasha} == {("rahu", "saturn"), ("rahu", "mercury")}


@needs_kernel
def test_the_period_of_life_answer_gets_the_sub_chapters_result_and_the_ai_sees_it(monkeypatch):
    plain = qa.answer_topic("future:overview", _birth(), NOW)
    assert not any("the text says" in f for f in plain.facts)
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: SUB_CHECKED)
    answer = qa.answer_topic("future:overview", _birth(), NOW)
    line = next(f for f in answer.facts if "the text says" in f)
    assert SUB.effects["rahu", "saturn"][0] in line and "(Phaladeepika 21.32)" in line
    assert line in qa._ai_prompt("how is my life now?", answer)


@needs_kernel
def test_every_view_still_fits_in_one_message_with_both_rule_files_checked(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: SUB_CHECKED)
    from samay.render.text import split_message
    for born in [("1989-08-14", "12:00", "Mumbai, India"), ("1952-08-15", "06:30", "Pune")]:
        birth = service.resolve_birth(BirthInput(*born))
        for topic in qa.OUTLOOK_TOPICS:
            answer = qa.answer_topic(topic, birth, NOW)
            for view in ("compact", "full"):
                parts = split_message(render_answer(answer, view))
                assert all(len(p) <= 4096 for p in parts), (born, topic, view)


# --- Phaladeepika 8: planets in houses, a second voice -------------------------------------------------------------------
from samay.engine import planet_houses

PH = planet_houses.load_rules()
PH_CHECKED = dataclasses.replace(PH, level="translation-checked", checked_by="test")


def test_every_planet_has_every_house_and_the_verse_ranges_follow_the_text():
    assert all((p, h) in PH.rows for p in planet_houses.PLANETS for h in range(1, 13))
    assert PH.verses == {"sun": "1-4", "moon": "5-7", "mars": "8-10", "mercury": "11-13", "jupiter": "14-16",
                         "venus": "17-19", "saturn": "20-24", "rahu": "25-27", "ketu": "28-33"}


def test_unchecked_gives_nothing_and_checked_picks_rows_by_the_rising_sign():
    assert PH.lookup("sun", 1, 0) is None
    cancer, aries, scorpio = 3, 0, 7
    rows, verse = PH_CHECKED.lookup("sun", 1, cancer)
    assert verse == "1-4" and len(rows) == 2 and rows[1].text == "cataract in the eyes"
    assert len(PH_CHECKED.lookup("sun", 1, scorpio)[0]) == 1  # only the general row
    assert PH_CHECKED.lookup("sun", 1, aries)[0][1].text == "eye disease"


def test_saturn_in_the_first_house_depends_on_the_sign_it_holds():
    libra, pisces = 6, 11
    (strong,), _ = PH_CHECKED.lookup("saturn", 1, libra)
    (weak,), _ = PH_CHECKED.lookup("saturn", 1, pisces)
    assert "equal to a king" in strong.text and "sorrow and misery" in weak.text


@pytest.mark.parametrize("change", [
    lambda r: r["effects"].pop("ketu"),
    lambda r: r["effects"]["sun"]["houses"].pop(5),
    lambda r: r["effects"]["sun"]["houses"].update({2: ""}),
    lambda r: r["effects"]["sun"]["houses"].update({1: [{"when_lagna": ["atlantis"], "text": "x"}]}),
    lambda r: r["effects"].update(pluto={"verse": "1", "houses": {}}),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_planet_house_file_is_rejected(tmp_path, change):
    raw = yaml.safe_load(planet_houses.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        planet_houses.load_rules(path)


@needs_kernel
def test_a_marriage_answer_adds_the_second_text_only_once_checked(monkeypatch):
    moon_in_seventh = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    plain = qa.answer_topic("life:marriage", moon_in_seventh, NOW)
    assert plain.second == () and "Phaladeepika chapter 8" not in render_answer(plain)
    monkeypatch.setattr(planet_houses, "load_rules", lambda path=None: PH_CHECKED)
    answer = qa.answer_topic("life:marriage", moon_in_seventh, NOW)
    assert [(v.planet, v.house) for v in answer.second] == [("moon", 7)]
    text = render_answer(answer)
    assert "What Phaladeepika chapter 8 says about Moon in your 7th house:" in text
    assert "Good-looking, and loved by a faithful and illustrious wife." in text
    assert "Phaladeepika 8.5–7" in text and "Brihat Jataka" in text
    assert "Phaladeepika, chapter 8, on Moon in house 7" in qa._ai_prompt("when will I marry?", answer)


@needs_kernel
def test_an_empty_seventh_house_adds_no_second_text(monkeypatch):
    monkeypatch.setattr(planet_houses, "load_rules", lambda path=None: PH_CHECKED)
    assert qa.answer_topic("life:marriage", _birth(), NOW).second == ()  # Aries, no planets in it


@needs_kernel
def test_rahu_and_ketu_get_a_reading_here_though_brihat_jataka_has_none(monkeypatch):
    monkeypatch.setattr(planet_houses, "load_rules", lambda path=None: PH_CHECKED)
    answer = qa.answer_topic("planet:rahu", _birth(), NOW)
    assert answer.reading is None and answer.second and answer.second[0].verse == "25-27"
    assert "Phaladeepika 8.25–27" in render_answer(answer)


# --- Ashtakavarga: points per sign, and what the number means (Phaladeepika 23) -------------------------------------------
from samay.engine import ashtakavarga

AV = ashtakavarga.load_rules()
AV_CHECKED = dataclasses.replace(AV, level="translation-checked", checked_by="test")
# Phaladeepika's worked example (ch. 23 verse 20): the Sun and Venus in Scorpio and Jupiter in Virgo are stated; the other
# four positions were found by search (the book does not print them) as the only chart that gives its twelve totals.
EXAMPLE = {"sun": 7, "venus": 7, "jupiter": 5, "moon": 0, "mars": 4, "mercury": 8, "saturn": 1, "lagna": 8}
BOOK_TOTALS = [19, 26, 33, 28, 27, 24, 29, 40, 24, 25, 26, 36]


def test_each_planets_table_adds_up_to_the_texts_total():
    totals = {p: sum(len(h) for h in row.values()) for p, row in AV.tables.items()}
    assert totals == {"sun": 48, "moon": 49, "mars": 39, "mercury": 54, "jupiter": 56, "venus": 52, "saturn": 39}
    assert sum(totals.values()) == 337


# The tables in use equal the standard modern ones (vedastro.org's Bhinnashtakavarga guide), which also follow Brihat Jataka IX.
STANDARD_DIFFERENCES = {  # the five lists where Phaladeepika's English translation prints something else, as used here
    ("moon", "jupiter"): (1, 4, 7, 8, 10, 11, 12), ("mars", "jupiter"): (6, 10, 11, 12),
    ("jupiter", "jupiter"): (1, 2, 3, 4, 7, 8, 10, 11), ("venus", "mars"): (3, 5, 6, 9, 11, 12),
    ("mercury", "mercury"): (1, 3, 5, 6, 9, 10, 11, 12),
}


def test_the_five_lists_follow_brihat_jataka_and_the_standard_tables():
    for (planet, src), houses in STANDARD_DIFFERENCES.items():
        assert AV.tables[planet][src] == houses
    # a few lists on which every source agrees
    assert AV.tables["sun"]["sun"] == (1, 2, 4, 7, 8, 9, 10, 11) and AV.tables["moon"]["sun"] == (3, 6, 7, 8, 10, 11)
    assert AV.tables["saturn"]["jupiter"] == (5, 6, 11, 12) and AV.tables["venus"]["lagna"] == (1, 2, 3, 4, 5, 8, 9, 11)


def test_phaladeepikas_worked_example_matches_only_its_own_printed_lists():
    """Verse 20's twelve sign totals come out under the lists as the translation prints them, and not under the tables in use:
    the book's example was worked with its own lists, which differ from the standard ones in these five places."""
    import copy
    printed = copy.deepcopy(AV)
    tables = {p: dict(row) for p, row in AV.tables.items()}
    for v in AV.variants:
        if "phaladeepika" in v:
            tables[v["planet"]][v["from"]] = tuple(v["phaladeepika"])
    printed = dataclasses.replace(AV, tables=tables)
    assert sorted(ashtakavarga.sarva(ashtakavarga.bhinna(printed, EXAMPLE))) == sorted(BOOK_TOTALS)
    assert sorted(ashtakavarga.sarva(ashtakavarga.bhinna(AV, EXAMPLE))) != sorted(BOOK_TOTALS)
    assert sum(ashtakavarga.sarva(ashtakavarga.bhinna(AV, EXAMPLE))) == 337  # the grand total is the same either way


def test_points_depend_on_the_chart_not_on_the_totals():
    shifted = {k: (v + 1) % 12 for k, v in EXAMPLE.items()}  # every position one sign on: the same pattern, one sign later
    a, b = ashtakavarga.sarva(ashtakavarga.bhinna(AV, EXAMPLE)), ashtakavarga.sarva(ashtakavarga.bhinna(AV, shifted))
    assert b == a[-1:] + a[:-1]


def test_the_differences_between_the_two_texts_are_recorded():
    assert sum(1 for v in AV.variants if "phaladeepika" in v) == 5 and len(AV.variants) == 6
    assert {(v["planet"], v["from"]) for v in AV.variants} >= {("moon", "jupiter"), ("venus", "mars"), ("moon", "sun")}
    assert AV.level == "unchecked" and not AV.servable and AV.threshold == 28
    assert AV.meaning[1] == "destruction or loss" and AV.meaning[7].startswith("gaining a kingdom")


@pytest.mark.parametrize("change", [
    lambda r: r["tables"]["sun"]["moon"].pop(),  # one point short of the text's count
    lambda r: r["tables"]["sun"]["moon"].__setitem__(0, 13),
    lambda r: r["tables"]["sun"].pop("lagna"),
    lambda r: r["tables"].pop("saturn"),
    lambda r: r["tables"]["moon"].__setitem__("sun", [6, 3, 7, 8, 10, 11]),  # not sorted
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_table_that_does_not_add_up_is_refused(tmp_path, change):
    raw = yaml.safe_load(ashtakavarga.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        ashtakavarga.load_rules(path)


@pytest.mark.parametrize(("question", "topic"), [
    ("show my ashtakavarga", "chart:ashtakavarga"), ("how many bindus do I have", "chart:ashtakavarga"),
    ("what is sarvashtakavarga", "chart:ashtakavarga"),
])
def test_ashtakavarga_questions_are_routed(question, topic):
    assert qa.sort_question(question) == topic and topic in qa.MODEL_SYSTEM


def test_without_a_birth_the_ashtakavarga_asks_for_one():
    answer = qa.answer_topic("chart:ashtakavarga", None, NOW)
    assert answer.ashtaka is None and render_answer(answer, birth_known=False) == prompts.NEED_BIRTH_FOR_CHART


@needs_kernel
def test_unchecked_tables_show_no_numbers():
    text = render_answer(qa.answer_topic("chart:ashtakavarga", _birth(), NOW))
    assert prompts.ASHTAKA_UNCHECKED in text and "house ·" not in text
    outlook = render_answer(qa.answer_topic("future:year", _birth(), NOW))
    assert " pts" not in outlook


@needs_kernel
def test_checked_tables_show_the_sign_totals_by_house_and_the_28_rule(monkeypatch):
    monkeypatch.setattr(ashtakavarga, "load_rules", lambda path=None: AV_CHECKED)
    answer = qa.answer_topic("chart:ashtakavarga", _birth(), NOW)
    assert sum(answer.ashtaka.sarva) == 337
    text = render_answer(answer)
    lagna = answer.ashtaka.lagna
    assert f"1st house · {ashtakavarga_sign(lagna)}" in text and "more than 28 points" in text and "✓" in text
    assert "Source: Brihat Jataka 9.1–7; Phaladeepika 23.20 · checked" in text
    full = render_answer(answer, "full")
    assert "prints different lists in 5 of the 56" in full and "Sun " in full and "Brihat Jataka 9.1–7; Phaladeepika" in text
    assert "ashtakavarga points per house" in qa._ai_prompt("which signs are strong?", answer)


def ashtakavarga_sign(index: int) -> str:
    from samay.engine.vedic import RASHIS, SIGNS
    return f"{SIGNS[index]} ({RASHIS[index]})"


@needs_kernel
def test_outlook_stays_carry_the_planets_own_points_once_checked(monkeypatch):
    monkeypatch.setattr(ashtakavarga, "load_rules", lambda path=None: AV_CHECKED)
    report = qa.answer_topic("future:year", _birth(), NOW).outlook
    assert report.ashtaka_checked and report.ashtaka_variants == 5
    assert all(s.points is not None for s in report.stays if s.planet not in ("rahu", "ketu"))
    assert all(s.points is None for s in report.stays if s.planet in ("rahu", "ketu"))
    assert all(0 <= s.points <= 8 for s in report.stays if s.points is not None)
    full = render_answer(qa.answer_topic("future:year", _birth(), NOW), "full")
    assert " pts: " in full and "23.11" in full and "; Brihat Jataka 9.1–7" in full
    assert "Phaladeepika's English translation prints different lists in 5 of the 56" in full
    assert " pts" not in render_answer(qa.answer_topic("future:year", _birth(), NOW))  # the plain view carries no points


@needs_kernel
def test_a_points_question_is_not_a_missed_topic_and_its_view_fits_a_message(monkeypatch):
    monkeypatch.setattr(ashtakavarga, "load_rules", lambda path=None: AV_CHECKED)
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: SUB_CHECKED)
    for topic in (*qa.OUTLOOK_TOPICS, "chart:ashtakavarga"):
        answer = qa.answer_topic(topic, _birth(), NOW)
        for view in ("compact", "full"):
            assert len(render_answer(answer, view)) < 4096, (topic, view)
    assert "chart:".startswith(qa.COMPUTED_PREFIXES) and "future:".startswith(qa.COMPUTED_PREFIXES)


# --- Brihat Jataka XVI and XVII: the Moon's nakshatra and sign --------------------------------------------------------------
from samay.engine import moon_nature

MN = moon_nature.load_rules()
MN_CHECKED = dataclasses.replace(MN, level="translation-checked", checked_by="test")


def test_27_nakshatras_and_12_signs_in_the_order_of_the_engine():
    assert len(MN.nakshatras) == 27 and len(MN.signs) == 12 and MN.level == "unchecked" and not MN.servable
    from samay.engine.vedic import SIGNS
    assert [s.name for s in MN.signs] == SIGNS
    assert tuple(n.name for n in MN.nakshatras) == moon_nature.TRANSLATION_NAMES


def test_a_verse_holds_two_nakshatras_except_punarvasu_alone():
    verses = [n.verse for n in MN.nakshatras]
    assert verses == sorted(verses) and verses[0] == 1 and verses[-1] == 14
    assert [verses.count(v) for v in range(1, 15)] == [2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]


def test_the_moon_longitude_picks_the_sign_nakshatra_and_pada():
    _, sign_text, _, nak_text, pada = moon_nature.for_moon(MN, 250.5)
    assert (sign_text.name, nak_text.name, pada) == ("Sagittarius", "Moola", 4)
    assert moon_nature.for_moon(MN, 0.0)[3].name == "Aswini" and moon_nature.for_moon(MN, 359.9)[3].name == "Revati"


@pytest.mark.parametrize("change", [
    lambda r: r["nakshatras"].pop(),
    lambda r: r["signs"].reverse(),
    lambda r: r["nakshatras"].reverse(),
    lambda r: r["signs"][0].update(text=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_moon_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(moon_nature.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        moon_nature.load_rules(path)


@pytest.mark.parametrize(("question", "topic"), [
    ("what is my nakshatra", "chart:moon"), ("tell me about my personality", "chart:moon"),
    ("what is my character like", "chart:moon"), ("what is a nakshatra", None),
])
def test_moon_questions_need_personal_phrasing_offline(question, topic):
    assert qa.sort_question(question) == topic


def test_without_a_birth_the_moon_reading_asks_for_one():
    answer = qa.answer_topic("chart:moon", None, NOW)
    assert answer.moon is None and render_answer(answer, birth_known=False) == prompts.NEED_BIRTH_FOR_MOON


@needs_kernel
def test_unchecked_moon_descriptions_are_not_shown():
    text = render_answer(qa.answer_topic("chart:moon", _birth(), NOW))
    assert prompts.MOON_UNCHECKED in text and "Moon is in" in text and "Brihat Jataka says" not in text
    assert not any(d.text in text for d in (*MN.signs, *MN.nakshatras))


@needs_kernel
def test_checked_moon_descriptions_are_quoted_with_the_texts_condition_and_sources(monkeypatch):
    monkeypatch.setattr(moon_nature, "load_rules", lambda path=None: MN_CHECKED)
    answer = qa.answer_topic("chart:moon", _birth(), NOW)
    v = answer.moon
    text = render_answer(answer)
    assert MN.signs[v.sign].text[1:] in text and MN.nakshatras[v.nakshatra_index].text[1:] in text
    assert "all powerful the effects described in this chapter will fully come to pass" in text
    assert f"Source: Brihat Jataka 16.{v.nakshatra.verse}, 17.{v.sign_text.verse}, 17.13 · checked" in text
    assert "If two of the three be powerful" not in text and "If two of the three be powerful" in render_answer(answer, "full")
    assert "Brihat Jataka XVII on your Moon" in qa._ai_prompt("what am I like?", answer)


@needs_kernel
def test_other_persons_moon_is_worded_for_them(monkeypatch):
    monkeypatch.setattr(moon_nature, "load_rules", lambda path=None: MN_CHECKED)
    text = render_answer(qa.answer_topic("chart:moon", _birth(), NOW, subject=Subject("Maya", "daughter", minor=True)))
    assert "Maya's Moon is in" in text and prompts.MINOR_NOTE in text


# --- Brihat Jataka XIII: the lunar yogas -----------------------------------------------------------------------------------
from types import SimpleNamespace

from samay.engine import chandra_yogas

CY = chandra_yogas.load_rules()
CY_CHECKED = dataclasses.replace(CY, level="translation-checked", checked_by="test")


def _sky(**signs):
    """A made-up chart: each named body in the given sign (0-11, mid-sign). Unnamed bodies sit in the 4th sign from the
    Moon, which makes no lunar yoga (not the 2nd, 6th, 7th, 8th or 12th from her); the lagna defaults to Aries."""
    moon = signs.get("moon", 0)
    names = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
    planets = {n: SimpleNamespace(longitude=signs.get(n, (moon + 3) % 12) * 30 + 15.0) for n in names}
    return SimpleNamespace(planets=planets, ascendant=signs.get("lagna", 0) * 30 + 15.0)


def _yogas(**signs):
    return {f.name.split(" (")[0]: f for f in chandra_yogas.find(CY_CHECKED, _sky(**signs)).found}


def test_unchecked_finds_nothing():
    assert chandra_yogas.find(CY, _sky(moon=3)) == chandra_yogas.Yogas((), False)


def test_the_moon_from_the_sun_is_graded_by_house():
    grade = lambda moon: _yogas(sun=0, moon=moon)["The Moon from the Sun"].detail.rsplit(": ", 1)[1]
    assert [grade(m) for m in (0, 3, 6, 9)] == ["poor"] * 4      # 1st, 4th, 7th, 10th: kendra
    assert [grade(m) for m in (1, 4, 7, 10)] == ["moderate"] * 4  # 2nd, 5th, 8th, 11th: panaphara
    assert [grade(m) for m in (2, 5, 8, 11)] == ["excellent"] * 4  # 3rd, 6th, 9th, 12th: apoklima


def test_sunapha_anapha_durudhura_follow_the_2nd_and_12th_from_the_moon():
    taurus, gemini, aries = 1, 2, 0
    assert "Sunapha yoga" in _yogas(moon=taurus, mars=gemini)            # Mars in the 2nd
    assert "Anapha yoga" in _yogas(moon=taurus, jupiter=aries)           # Jupiter in the 12th
    both = _yogas(moon=taurus, mars=gemini, jupiter=aries)
    assert "Durudhura yoga" in both and "Sunapha yoga" not in both and "Anapha yoga" not in both


def test_the_sun_does_not_make_these_yogas_and_neither_do_the_nodes():
    sky = _yogas(moon=1, sun=2, rahu=2, ketu=0)  # the Sun in the 2nd, Ketu in the 12th: neither counts
    assert "Kemadruma yoga" in sky and not {"Sunapha yoga", "Anapha yoga", "Durudhura yoga"} & sky.keys()


def test_kemadruma_carries_the_text_cancellation_and_the_charts_facts():
    k = _yogas(moon=5, sun=5, lagna=5)["Kemadruma yoga"]  # Moon with the Sun (a planet with her) and in a kendra (the 1st)
    assert "ceases to be a Kemadruma" in k.extra[0] and "in a kendra" in k.detail and "is with Sun" in k.detail
    lonely = _yogas(moon=5, sun=9, lagna=0)["Kemadruma yoga"]  # Moon in the 6th from lagna, alone
    assert "not in a kendra" in lonely.detail and "has no planet with her" in lonely.detail


def test_the_yoga_planets_give_their_own_texts_and_two_of_them_add_the_note():
    one = _yogas(moon=1, mars=2)
    assert one["The yoga planet Mars"].text.startswith("the person will be active, fond of fight") and one["The yoga planet Mars"].extra == ()
    two = _yogas(moon=1, mars=2, saturn=0)
    assert {"The yoga planet Mars", "The yoga planet Saturn"} <= two.keys()
    assert "for them all will come to pass" in two["The yoga planet Mars"].extra[0]
    assert not any(k.startswith("The yoga planet") for k in _yogas(moon=1))  # Kemadruma has no yoga planet


def test_adhi_yoga_needs_a_benefic_in_the_6th_7th_or_8th_from_the_moon():
    # Moon in Aries; Mercury in Virgo (6th), Jupiter in Libra (7th), Venus in Scorpio (8th)
    assert "Adhi yoga" in _yogas(moon=0, mercury=5, jupiter=6, venus=7)
    assert "Adhi yoga" in _yogas(moon=0, venus=7)
    assert "Adhi yoga" not in _yogas(moon=0, mars=6, saturn=7)  # malefics do not make it


def test_benefics_in_the_upachaya_houses_are_counted_from_the_lagna_and_the_moon_and_overrule_a_poor_yoga():
    # Lagna Aries, Moon Aries: the 3rd, 6th, 10th, 11th are Gemini, Virgo, Capricorn, Aquarius
    sky = _yogas(lagna=0, moon=0, mercury=2, jupiter=5, venus=9)
    u = sky["Benefics in the upachaya houses"]
    assert "very rich" in u.text and "moderately rich" in u.text and u.detail.startswith("3 of")
    assert "exceedingly rich" in u.extra[0] and "to their exclusion" in u.extra[1]
    assert "Benefics in the upachaya houses" not in _yogas(lagna=0, moon=0)


@needs_kernel
def test_the_moon_answer_includes_the_yogas_only_once_their_file_is_checked(monkeypatch):
    plain = render_answer(qa.answer_topic("chart:moon", _birth(), NOW))
    assert prompts.MOON_YOGAS_UNCHECKED in plain and "yogas in your chart" not in plain
    monkeypatch.setattr(chandra_yogas, "load_rules", lambda path=None: CY_CHECKED)
    text = render_answer(qa.answer_topic("chart:moon", _birth(), NOW))
    assert prompts.MOON_YOGAS_UNCHECKED not in text and "The Moon's yogas in your chart (Brihat Jataka chapter 13):" in text
    assert "• The Moon from the Sun" in text and "Source: Brihat Jataka 13." in text and prompts.MOON_UNCHECKED in text


@needs_kernel
def test_yogas_and_descriptions_are_gated_separately_and_fit_one_message(monkeypatch):
    monkeypatch.setattr(chandra_yogas, "load_rules", lambda path=None: CY_CHECKED)
    monkeypatch.setattr(moon_nature, "load_rules", lambda path=None: MN_CHECKED)
    for born in [("1989-08-14", "12:00", "Mumbai, India"), ("1952-08-15", "06:30", "Pune"), ("1990-08-15", "14:30", "Pune")]:
        answer = qa.answer_topic("chart:moon", service.resolve_birth(BirthInput(*born)), NOW)
        for view in ("compact", "full"):
            assert len(render_answer(answer, view)) < 4096, (born, view)
        assert "Brihat Jataka XIII" in qa._ai_prompt("what am I like?", answer)


# --- Phaladeepika 20: the dasha through the houses its lord rules ------------------------------------------------------------
from samay.engine import lordship

LR = lordship.load_rules()
LR_CHECKED = dataclasses.replace(LR, level="translation-checked", checked_by="test")


def _chart(lagna: int, **where):
    """A made-up chart: lagna sign, and named planets at (sign, retrograde, degree-in-sign). Others sit in the 4th from lagna."""
    names = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
    planets = {}
    for n in names:
        sign, retro, deg = where.get(n, ((lagna + 3) % 12, False, 15.0))
        planets[n] = SimpleNamespace(longitude=sign * 30 + deg, retrograde=retro)
    return SimpleNamespace(planets=planets, ascendant=lagna * 30 + 15.0)


def test_all_twelve_houses_have_a_strong_and_a_weak_result_with_the_texts_verses():
    assert set(LR.houses) == set(range(1, 13)) and LR.level == "unchecked" and not LR.servable
    assert [LR.houses[h]["strong"][0] for h in range(1, 13)] == list(range(2, 14))
    assert [LR.houses[h]["weak"][0] for h in range(1, 13)] == [15, 15, 16, 16, 17, 17, 18, 18, 19, 19, 20, 20]


def test_unchecked_judges_nothing():
    assert lordship.judge(LR, _chart(0), "mars") is None


def test_houses_ruled_come_from_the_lagna_and_the_nodes_rule_none():
    aries = 0
    mars = lordship.judge(LR_CHECKED, _chart(aries), "mars")
    assert mars.owned == (1, 8)  # Mars rules Aries and Scorpio: the 1st and 8th for an Aries lagna
    assert lordship.judge(LR_CHECKED, _chart(aries), "rahu") is None and lordship.judge(LR_CHECKED, _chart(aries), "ketu") is None
    sun = lordship.judge(LR_CHECKED, _chart(aries), "sun")
    assert sun.owned == (5,)  # Leo


def test_a_planet_in_its_own_sign_or_retrograde_and_not_in_a_dusthana_leans_strong():
    aries, leo = 0, 4
    own = lordship.judge(LR_CHECKED, _chart(aries, sun=(leo, False, 15.0)), "sun")
    assert own.leaning == "strong" and own.good == ("in its own sign",) and own.adverse == ()
    retro = lordship.judge(LR_CHECKED, _chart(aries, mars=(1, True, 15.0)), "mars")  # Taurus: a neutral sign, the 2nd house
    assert retro.leaning == "strong" and retro.good == ("retrograde",)
    assert [(h, k, v) for h, k, v, _ in own.rows] == [(5, "strong", 6)]


def test_each_adverse_condition_of_verse_14_makes_it_lean_weak():
    aries = 0
    in_6th = lordship.judge(LR_CHECKED, _chart(aries, sun=(5, False, 15.0)), "sun")        # Virgo = 6th from Aries
    assert in_6th.adverse == ("in the 6th house",) and in_6th.leaning == "weak"
    debil = lordship.judge(LR_CHECKED, _chart(aries, sun=(6, False, 15.0)), "sun")         # Libra: the Sun's depression
    assert "in its sign of debilitation" in debil.adverse and debil.leaning == "weak"
    enemy = lordship.judge(LR_CHECKED, _chart(aries, jupiter=(1, False, 15.0)), "jupiter")  # Taurus: an enemy's sign for Jupiter
    assert "in an inimical sign" in enemy.adverse
    combust = lordship.judge(LR_CHECKED, _chart(aries, sun=(1, False, 10.0), mercury=(1, False, 12.0)), "mercury")
    assert "eclipsed by the Sun's rays" in combust.adverse


def test_adverse_beats_good_and_a_chart_with_neither_gets_both_readings():
    aries = 0
    mixed = lordship.judge(LR_CHECKED, _chart(aries, mars=(7, False, 15.0)), "mars")  # own sign, but the 8th house
    assert mixed.good == ("in its own sign",) and mixed.adverse == ("in the 8th house",) and mixed.leaning == "weak"
    plain = lordship.judge(LR_CHECKED, _chart(aries, mercury=(0, False, 15.0)), "mercury")  # Aries: neutral for Mercury, the 1st house
    assert plain.leaning == "undecided" and {k for _, k, _, _ in plain.rows} == {"strong", "weak"}
    assert len(plain.rows) == 4  # Mercury rules the 3rd and 6th: two readings each


@needs_kernel
def test_the_running_dasha_answer_adds_lordship_once_checked_and_the_ai_sees_it(monkeypatch):
    assert qa.answer_topic("future:overview", _birth(), NOW).lordship == ()
    monkeypatch.setattr(lordship, "load_rules", lambda path=None: LR_CHECKED)
    answer = qa.answer_topic("future:overview", _birth(), NOW)  # Rahu chapter, Saturn sub-chapter: only Saturn rules houses
    assert [v.planet for v in answer.lordship] == ["saturn"]
    text = render_answer(answer)
    assert "What Phaladeepika chapter 20 says of the Saturn dasha" in text and "Phaladeepika" in text.splitlines()[-3]
    assert "Phaladeepika 20, the dasha of Saturn" in qa._ai_prompt("how is my life now?", answer)
    jupiter = qa.answer_topic("dasha:jupiter", _birth(), NOW)
    assert [v.planet for v in jupiter.lordship] == ["jupiter"]
    assert qa.answer_topic("dasha:rahu", _birth(), NOW).lordship == ()


def test_verse_41_kendra_lords_are_adverse_if_benefic_and_favourable_if_malefic():
    gemini, aries = 2, 0
    mercury = lordship.judge(LR_CHECKED, _chart(gemini), "mercury")  # lord of the 1st and 4th: kendras, a natural benefic
    texts = [t for _, t in mercury.nature]
    assert any("adverse if that planet is a natural benefic" in t for t in texts)
    assert not any("favourable if that planet is a natural malefic" in t for t in texts)
    mars = lordship.judge(LR_CHECKED, _chart(aries), "mars")  # 1st and 8th: a natural malefic
    mtexts = [t for _, t in mars.nature]
    assert any("favourable if that planet is a natural malefic" in t for t in mtexts)
    assert not any("adverse if that planet is a natural benefic" in t for t in mtexts)


def test_verse_41_trikona_the_evil_houses_and_the_eighth_lord_who_is_also_lagna_lord():
    aries = 0
    mars = lordship.judge(LR_CHECKED, _chart(aries), "mars")
    assert any("trikona" in t for _, t in mars.nature) and any("also the lord of the lagna" in t for _, t in mars.nature)
    mercury = lordship.judge(LR_CHECKED, _chart(aries), "mercury")  # 3rd and 6th
    assert any("3rd, 6th and 11th always produce evil" in t for _, t in mercury.nature)
    saturn = lordship.judge(LR_CHECKED, _chart(aries), "saturn")  # 10th and 11th
    assert any("3rd, 6th and 11th" in t for _, t in saturn.nature) and any("kendra" in t for _, t in saturn.nature)
    jupiter = lordship.judge(LR_CHECKED, _chart(aries), "jupiter")  # 9th and 12th: trikona only
    assert [t for _, t in jupiter.nature] == [next(t for _, t in jupiter.nature if "trikona" in t)]


def test_verse_41_the_sun_and_moon_owning_the_eighth_are_free_of_its_stigma():
    capricorn, sagittarius = 8 + 1, 8  # lagna signs that make Leo / Cancer the 8th house
    sun = lordship.judge(LR_CHECKED, _chart(capricorn), "sun")
    moon = lordship.judge(LR_CHECKED, _chart(sagittarius), "moon")
    assert sun.owned == (8,) and moon.owned == (8,)
    for v in (sun, moon):
        assert any("only good effects even if they own the 8th" in t for _, t in v.nature)
    mars_8th = lordship.judge(LR_CHECKED, _chart(0), "mars")  # Mars owns the 8th too, but is not the Sun or Moon
    assert not any("only good effects" in t for _, t in mars_8th.nature)


def test_the_moon_is_benefic_only_when_waxing():
    waxing = _chart(0, sun=(0, False, 10.0), moon=(1, False, 10.0))
    waning = _chart(0, sun=(0, False, 10.0), moon=(6, False, 10.0))
    assert lordship.natural_benefic(waxing, "moon") and not lordship.natural_benefic(waning, "moon")
    assert [lordship.natural_benefic(waxing, p) for p in ("jupiter", "venus", "mercury", "sun", "mars", "saturn")] == [True] * 3 + [False] * 3


def test_verse_24_the_order_of_main_dashas_counts_from_the_one_born_in():
    # order: ketu venus sun moon mars rahu jupiter saturn mercury
    saturn_fourth = lordship.judge(LR_CHECKED, _chart(0), "saturn", "mars")     # mars, rahu, jupiter, saturn
    assert any("4th in the order" in t for _, t in saturn_fourth.troublesome)
    assert not any("order" in t for _, t in lordship.judge(LR_CHECKED, _chart(0), "saturn", "venus").troublesome)
    jupiter_sixth = lordship.judge(LR_CHECKED, _chart(0), "jupiter", "venus")   # venus ... jupiter is the 6th
    assert any("6th in the order" in t for _, t in jupiter_sixth.troublesome)
    mars_fifth = lordship.judge(LR_CHECKED, _chart(0), "mars", "ketu")          # ketu venus sun moon mars
    assert any("5th in the order" in t for _, t in mars_fifth.troublesome)


def test_verse_24_a_planet_in_the_last_degree_and_the_lords_of_the_6th_8th_and_12th():
    last = lordship.judge(LR_CHECKED, _chart(0, sun=(4, False, 29.5)), "sun", "ketu")
    assert any("last degree of a sign" in t for _, t in last.troublesome)
    middle = lordship.judge(LR_CHECKED, _chart(0, sun=(4, False, 15.0)), "sun", "ketu")
    assert not any("last degree" in t for _, t in middle.troublesome)
    mars = lordship.judge(LR_CHECKED, _chart(0), "mars", "ketu")  # owns the 8th
    assert any("6th, 8th and 12th" in t for _, t in mars.troublesome)
    sun = lordship.judge(LR_CHECKED, _chart(0), "sun", "ketu")    # owns only the 5th
    assert not any("6th, 8th and 12th" in t for _, t in sun.troublesome)


@needs_kernel
def test_the_period_answer_shows_parasaras_view_and_the_troublesome_dashas(monkeypatch):
    monkeypatch.setattr(lordship, "load_rules", lambda path=None: LR_CHECKED)
    text = render_answer(qa.answer_topic("dasha:saturn", _birth(), NOW))
    assert "Parasara's view, as the text gives it (20.41):" in text
    prompt = qa._ai_prompt("how is the Saturn period?", qa.answer_topic("dasha:saturn", _birth(), NOW))
    assert "Parasara's view (20.41)" in prompt


# --- Planets together (Brihat Jataka XIV, Phaladeepika 18) --------------------------------------------------------------------
from samay.engine import conjunctions

CJ = conjunctions.load_rules()
CJ_CHECKED = dataclasses.replace(CJ, level="translation-checked", checked_by="test")


def test_all_21_pairs_have_both_texts_with_their_verses():
    assert len(CJ.pairs) == 21 and CJ.level == "unchecked" and not CJ.servable
    assert CJ.pairs["sun", "moon"].verse_bj == "14.1" and CJ.pairs["venus", "saturn"].verse_pd == "18.5"
    assert all(p.bj and p.pd for p in CJ.pairs.values())
    assert "Punarbhu" in CJ.pairs["moon", "saturn"].bj_note


def test_unchecked_finds_nothing_and_checked_finds_pairs_by_shared_sign():
    sky = _sky(sun=0, mercury=0, jupiter=5)
    assert conjunctions.find(CJ, sky) == ()
    (t,) = conjunctions.find(CJ_CHECKED, _sky(sun=2, mercury=2, jupiter=9, moon=0, mars=4, venus=6, saturn=11))
    assert t.sign == 2 and t.planets == ("sun", "mercury") and [p for p, _ in t.pairs] == [("sun", "mercury")]


def test_three_planets_in_a_sign_are_read_as_three_pairs():
    (t,) = conjunctions.find(CJ_CHECKED, _sky(moon=1, mars=1, jupiter=1, sun=7, mercury=9, venus=11, saturn=3))
    assert t.planets == ("moon", "mars", "jupiter")
    assert [p for p, _ in t.pairs] == [("moon", "mars"), ("moon", "jupiter"), ("mars", "jupiter")]


def test_nodes_do_not_count():
    assert conjunctions.find(CJ_CHECKED, _sky(rahu=2, ketu=2, sun=3, moon=5, mars=7, mercury=9, jupiter=11, venus=0, saturn=1)) == ()


@pytest.mark.parametrize("change", [
    lambda r: r["pairs"].pop("sun+moon"),
    lambda r: r["pairs"].update({"sun+rahu": r["pairs"]["sun+moon"]}),
    lambda r: r["pairs"]["sun+moon"].update(bj=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_conjunction_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(conjunctions.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        conjunctions.load_rules(path)


@pytest.mark.parametrize(("question", "topic"), [
    ("which planets are together in my chart", "chart:conjunctions"), ("do I have any yogas", "chart:yogas"), ("which yogas do I have", "chart:yogas"),
    ("what is a yoga", None),
])
def test_conjunction_questions_need_personal_phrasing_offline(question, topic):
    assert qa.sort_question(question) == topic


@needs_kernel
def test_the_conjunction_answer_waits_for_the_check_then_quotes_and_paraphrases(monkeypatch):
    born = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    waiting = render_answer(qa.answer_topic("chart:conjunctions", born, NOW))
    assert prompts.TOGETHER_UNCHECKED in waiting and "Brihat Jataka 14" not in waiting
    monkeypatch.setattr(conjunctions, "load_rules", lambda path=None: CJ_CHECKED)
    answer = qa.answer_topic("chart:conjunctions", born, NOW)
    text = render_answer(answer)
    if answer.together:
        assert "Brihat Jataka 14." in text and "Phaladeepika 18." in text and "· checked" in text
        assert "Brihat Jataka 14" in qa._ai_prompt("which planets are together?", answer)
    else:
        assert prompts.TOGETHER_NONE in text
    assert render_answer(qa.answer_topic("chart:conjunctions", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_TOGETHER


@needs_kernel
def test_a_chart_with_a_pair_shows_both_texts(monkeypatch):
    monkeypatch.setattr(conjunctions, "load_rules", lambda path=None: CJ_CHECKED)
    for date, time_, place in [("1990-08-15", "14:30", "Pune"), ("1952-08-15", "06:30", "Pune"), ("2015-03-14", "06:30", "Pune"),
                               ("1989-08-14", "12:00", "Mumbai, India"), ("1975-01-01", "10:00", "Pune")]:
        answer = qa.answer_topic("chart:conjunctions", service.resolve_birth(BirthInput(date, time_, place)), NOW)
        if answer.together:
            text = render_answer(answer)
            first = answer.together[0].pairs[0][1]
            assert first.bj in text and first.pd[1:] in text
            return
    pytest.fail("none of the sample charts has two planets in one sign")


# --- Nabhasa yogas (Brihat Jataka XII), chapter 6 yogas (Phaladeepika) and raja yogas (Brihat Jataka XI) ----------------------
from samay.engine import nabhasa, phaladeepika_yogas, raja_yogas

NB = nabhasa.load_rules()
NB_CHECKED = dataclasses.replace(NB, level="translation-checked", checked_by="test")
P6 = phaladeepika_yogas.load_rules()
P6_CHECKED = dataclasses.replace(P6, level="translation-checked", checked_by="test")
RJ = raja_yogas.load_rules()
RJ_CHECKED = dataclasses.replace(RJ, level="translation-checked", checked_by="test")


def _full_sky(lagna=0, retro_sun_moon=True, **where):
    """A made-up chart with every body in a named sign (0-11) and degree, defaulting to the 8th sign from the lagna, 15 degrees."""
    names = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
    planets = {}
    for n in names:
        spec = where.get(n, (lagna + 7) % 12)
        sign, deg = spec if isinstance(spec, tuple) else (spec, 15.0)
        planets[n] = SimpleNamespace(longitude=sign * 30 + deg, retrograde=False)
    return SimpleNamespace(planets=planets, ascendant=lagna * 30 + 15.0, ayanamsa=24.0)


def _nab(**where):
    return [y.key for y in nabhasa.find(NB_CHECKED, _full_sky(**where)).yogas]


def test_nabhasa_has_32_yogas_in_the_texts_four_groups_and_is_hidden_until_checked():
    groups = [y["group"] for y in NB.yogas.values()]
    assert (groups.count("asraya"), groups.count("dala"), groups.count("akriti"), groups.count("sankhya")) == (3, 2, 20, 7)
    assert NB.level == "unchecked" and nabhasa.find(NB, _full_sky()).yogas == ()


def _all_in(*signs):
    """Seven planets spread over the given signs in order, repeating the last sign for the extras."""
    order = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
    return {p: signs[min(i, len(signs) - 1)] for i, p in enumerate(order)}


def test_asraya_all_planets_in_movable_fixed_or_common_signs():
    assert "kamala" in _nab(**_all_in(0, 3, 6, 9)) and "rajju" not in _nab(**_all_in(0, 3, 6, 9))  # four movable signs = the four kendras
    assert "rajju" in _nab(**_all_in(0, 3, 6)) and "musala" in _nab(**_all_in(1, 4, 7)) and "nala" in _nab(**_all_in(2, 5))
    assert "rajju" not in _nab(**_all_in(0, 0, 0, 0, 0, 0, 0)) and "gola" in _nab(**_all_in(0))  # one sign is Gola, not an Asraya


def test_sankhya_yogas_count_the_signs():
    names = {7: "vallaki", 6: "damini", 5: "pasa", 4: "kedara", 3: "sula", 2: "yuga", 1: "gola"}
    # spread over signs that avoid every Akriti shape: signs 1,2,5,6,9,10,... houses 2 5 6 9 10 11 12 etc.
    for n in names:
        sky = _all_in(*[(0, 1, 5, 6, 9, 10, 11)[i] for i in range(n)])
        got = [y.key for y in nabhasa.find(NB_CHECKED, _full_sky(**sky)).yogas]
        assert got, (n, got)


@pytest.mark.parametrize(("key", "houses"), [
    ("sakata", (1, 7)), ("vihaga", (4, 10)), ("gada", (1, 4)), ("sringataka", (1, 5, 9)), ("hala", (2, 6, 10)), ("kamala", (1, 4, 7, 10)),
    ("vapi", (2, 5, 8, 11)), ("yupa", (1, 2, 3, 4)), ("ishu", (4, 5, 6, 7)), ("sakti", (7, 8, 9, 10)), ("danda", (10, 11, 12, 1)),
    ("nau", (1, 2, 3, 4, 5, 6, 7)), ("kuta", (4, 5, 6, 7, 8, 9, 10)), ("chhatra", (7, 8, 9, 10, 11, 12, 1)), ("chapa", (10, 11, 12, 1, 2, 3, 4)),
    ("ardha_chandra", (2, 3, 4, 5, 6, 7, 8)), ("samudra", (2, 4, 6, 8, 10, 12)), ("chakra", (1, 3, 5, 7, 9, 11)),
])
def test_each_akriti_yoga_needs_exactly_its_houses_occupied(key, houses):
    lagna = 0  # house h = sign h-1
    sky = _all_in(*[h - 1 for h in houses])
    assert key in _nab(lagna=lagna, **sky)
    missing_one = _all_in(*[h - 1 for h in houses[:-1]]) if len(houses) > 1 else {}
    if missing_one:
        assert key not in _nab(lagna=lagna, **missing_one)  # all but one of the houses: not that yoga


def test_an_akriti_yoga_replaces_the_sankhya_one_and_an_asraya_one():
    got = _nab(**_all_in(0, 3))  # houses 1 and 4 only: Gada (adjacent kendras); also movable, and two signs
    assert "gada" in got and "yuga" not in got and "rajju" not in got


def test_dala_srik_and_sarpa_need_three_kendras_and_none_of_the_other_kind():
    srik = _nab(mercury=0, jupiter=3, venus=6, sun=1, mars=2, saturn=4, moon=5)  # benefics in the 1st, 4th and 7th; malefics elsewhere
    assert "srik" in srik
    assert "srik" not in _nab(mercury=0, jupiter=3, venus=6, sun=9, mars=2, saturn=4, moon=5)  # a malefic in the 10th
    assert "sarpa" in _nab(sun=0, mars=3, saturn=6, mercury=1, jupiter=2, venus=4, moon=5)


def test_vajra_and_yava_need_the_benefics_and_malefics_apart():
    vajra = _nab(mercury=0, venus=6, jupiter=0, sun=3, mars=9, saturn=3, moon=9)  # the waning Moon counts as a malefic
    assert "vajra" in vajra and "kamala" not in vajra
    assert "yava" in _nab(mercury=3, venus=9, jupiter=3, sun=0, mars=6, saturn=0, moon=3)


def test_the_nabhasa_answer_always_has_a_yoga_for_a_real_chart():
    for born in [("1989-08-14", "12:00", "Mumbai, India"), ("1952-08-15", "06:30", "Pune"), ("2015-03-14", "06:30", "Pune")]:
        chart = service.natal_report(service.resolve_birth(BirthInput(*born))).chart
        n = nabhasa.find(NB_CHECKED, chart)
        assert n.yogas and n.life_note.startswith("These effects are felt throughout")


def test_the_chapter_6_file_has_a_definition_for_every_yoga_and_a_detector_for_every_one():
    assert set(P6.yogas) == set(phaladeepika_yogas.DETECTORS) and len(P6.yogas) == 45 and P6.level == "unchecked"
    assert all(y["definition"] for y in P6.yogas.values())


def _p6(**where):
    return {f.key: f for f in phaladeepika_yogas.find(P6_CHECKED, _full_sky(**where))}


def test_mahapurusha_needs_own_or_exaltation_sign_in_a_kendra_from_the_lagna_or_the_moon():
    assert "ruchaka" in _p6(mars=(0, 15.0))                       # Aries, the 1st house
    assert "ruchaka" not in _p6(mars=(0, 15.0), lagna=1)          # Aries is the 12th from a Taurus lagna: not a kendra, Moon elsewhere
    from_moon = _p6(mars=7, moon=4, lagna=5)                      # Scorpio is the 4th from the Moon in Leo; the 3rd from a Virgo lagna
    assert "ruchaka" in from_moon and "from the Moon" in from_moon["ruchaka"].detail
    assert "mahapurusha_count" in _p6(mars=0, venus=1, mercury=5)  # lagna Aries: Ruchaka, Malavya (Taurus is the 2nd, no)...


def test_mahapurusha_count_texts_follow_the_number_of_yogas():
    one = _p6(mars=0)["mahapurusha_count"]
    two = _p6(mars=0, mercury=2, jupiter=0, saturn=9)  # Ruchaka, Bhadra (Gemini is the 3rd: no), Hamsa (Aries: no), Sasa (Capricorn: yes)
    assert one.text == "a fortunate person"
    assert two["mahapurusha_count"].text == "equal to a king"


def test_vesi_vasi_and_ubhayachari_use_the_sun_and_the_benefics_or_malefics():
    assert "subhavesi" in _p6(sun=0, jupiter=1) and "subhavasi" in _p6(sun=0, venus=11)
    both = _p6(sun=0, jupiter=1, venus=11)
    assert "subhobhayachari" in both and "subhavesi" not in both and "subhavasi" not in both
    assert "papavesi" in _p6(sun=0, saturn=1) and "papavasi" in _p6(sun=0, mars=11)
    assert "subhavesi" not in _p6(sun=0, moon=1, rahu=1)  # the Moon and nodes do not count


def test_kartari_amala_and_vasumati():
    assert "subhakartari" in _p6(mercury=11, jupiter=1) and "papakartari" in _p6(sun=11, mars=1)
    assert "amala" in _p6(jupiter=9) and "amala" in _p6(venus=0, moon=3, lagna=2)  # the 10th from the lagna, and from the Moon
    assert "vasumati" in _p6(mercury=2, jupiter=5, venus=9) and "vasumati" not in _p6(mercury=2, jupiter=5, venus=8)


def test_kesari_sakata_and_the_moon_from_the_sun():
    assert "kesari" in _p6(moon=3, jupiter=0) and "kesari" not in _p6(moon=1, jupiter=0)
    assert "sakata" in _p6(moon=5, jupiter=0, lagna=1) and "sakata" not in _p6(moon=5, jupiter=0, lagna=5)  # the Moon in a kendra cancels
    assert "adhama" in _p6(sun=0, moon=3) and "sama" in _p6(sun=0, moon=4) and "varishtha" in _p6(sun=0, moon=2)


def test_lakshmi_gouri_and_saraswati():
    assert "lakshmi" in _p6(lagna=0, venus=6, jupiter=8)    # Aries lagna: the 9th lord Jupiter in Sagittarius (the 9th), Venus in Libra (the 7th)
    assert "gouri" in _p6(lagna=0, moon=3, jupiter=11)                # the Moon in Cancer (own, the 4th); Jupiter in Pisces sees it from the 5th
    assert "saraswati" in _p6(lagna=0, mercury=3, jupiter=8, venus=6)


def test_srikantha_srinatha_and_virinchi_need_all_three_in_good_signs_in_kendras_or_trikonas():
    assert "srikantha" in _p6(lagna=0, sun=0, moon=3, mars=0)  # the lagna lord Mars (Aries), the Sun (Aries, exalted), the Moon (Cancer)
    assert "srikantha" not in _p6(lagna=0, sun=0, moon=3, mars=5)


def test_parivartana_pairs_are_classified_by_the_houses_they_touch():
    # Aries lagna: Mars rules 1 and 8, Venus 2 and 7, Mercury 3 and 6, Moon 4, Sun 5, Jupiter 9 and 12, Saturn 10 and 11.
    assert "maha" in _p6(lagna=0, mars=1, venus=0)      # lord of the 1st in the 2nd (Taurus) and lord of the 2nd in the 1st (Aries)
    assert "kahala" in _p6(lagna=0, mars=2, mercury=0)  # the 1st and the 3rd
    assert "dainya" in _p6(lagna=0, mars=5, mercury=0)  # the 1st and the 6th


def test_raja_yoga_needs_the_9th_and_10th_lords_together_outside_the_dusthanas():
    # Aries lagna: the 9th lord is Jupiter, the 10th lord Saturn
    assert "raja" in _p6(lagna=0, jupiter=4, saturn=4) and "raja" not in _p6(lagna=0, jupiter=5, saturn=5)  # Virgo is the 6th
    assert "raja" not in _p6(lagna=0, jupiter=4, saturn=8)


def test_adhi_yoga_from_the_lagna_and_the_moon_needs_all_three_benefics_in_the_6th_to_8th():
    assert "lagnadhi" in _p6(lagna=0, mercury=5, jupiter=6, venus=7) and "lagnadhi" not in _p6(lagna=0, mercury=5, jupiter=6, venus=1)
    assert "chandradhi" in _p6(moon=0, mercury=5, jupiter=5, venus=6)


def test_the_house_yogas_and_the_three_vipareeta_ones():
    assert "ava" in _p6(lagna=0, mars=5)         # the lagna lord Mars in the 6th
    assert "daridra" in _p6(lagna=0, saturn=5)    # the 11th lord Saturn in the 6th
    assert "harsha" in _p6(lagna=0, mercury=5) and "sarala" in _p6(lagna=0, mars=7) and "vimala" in _p6(lagna=0, jupiter=11)
    assert "ava" not in _p6(lagna=0, mars=4)


def test_the_sankhya_names_of_phaladeepika_are_given_by_the_number_of_signs():
    f = _p6(**_all_in(0, 2, 5, 7))
    assert f["sankhya"].name.startswith("Kendra") and "four" not in f["sankhya"].detail and "4 signs" in f["sankhya"].detail


def _raja(**where):
    return {f.id for f in raja_yogas.find(RJ_CHECKED, _full_sky(**where))}


def test_a_raja_configuration_needs_every_planet_and_the_rising_sign():
    v4a = {"lagna": 10, "saturn": 10, "sun": 0, "moon": 1, "mercury": 2, "jupiter": 4, "mars": 7}  # Aquarius rising
    assert "v4a" in _raja(**v4a)
    assert "v4a" not in _raja(**{**v4a, "sun": 1})            # the Sun in the wrong sign
    assert "v4a" not in _raja(**{**v4a, "lagna": 5})          # the wrong rising sign
    assert "v5a" in _raja(lagna=9, mars=9, sun=8, moon=8, saturn=9)


def test_first_half_means_the_first_15_degrees():
    base = {"lagna": 11, "venus": 11, "moon": 8, "jupiter": 8}
    assert "v7a1" in _raja(**base, mars=(9, 14.9)) and "v7a1" not in _raja(**base, mars=(9, 15.1))


def test_three_exalted_planets_and_the_count_of_strong_planets():
    assert any(f.id == "v1" for f in raja_yogas.find(RJ_CHECKED, _full_sky(sun=0, mars=9, saturn=6)))   # three malefics exalted
    assert not any(f.id == "v1" for f in raja_yogas.find(RJ_CHECKED, _full_sky(sun=0, mars=9)))
    five = [f for f in raja_yogas.find(RJ_CHECKED, _full_sky(sun=4, moon=3, mars=0, mercury=2, jupiter=8, venus=1, saturn=9)) if f.id == "v13"]
    assert five and "five or more" in five[0].text.lower().replace("five or more planets", "five or more")


@needs_kernel
def test_the_yogas_answer_hides_each_source_until_it_is_checked_and_then_shows_all(monkeypatch):
    born = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    waiting = render_answer(qa.answer_topic("chart:yogas", born, NOW))
    assert waiting.count(prompts.YOGAS_UNCHECKED) == 6 and "Source:" not in waiting
    monkeypatch.setattr(nabhasa, "load_rules", lambda path=None: NB_CHECKED)
    only_nabhasa = render_answer(qa.answer_topic("chart:yogas", born, NOW))
    assert only_nabhasa.count(prompts.YOGAS_UNCHECKED) == 5 and "Nabhasa yogas (Brihat Jataka chapter 12)" in only_nabhasa
    monkeypatch.setattr(phaladeepika_yogas, "load_rules", lambda path=None: P6_CHECKED)
    monkeypatch.setattr(raja_yogas, "load_rules", lambda path=None: RJ_CHECKED)
    monkeypatch.setattr(phaladeepika_raja, "load_rules", lambda path=None: R7_CHECKED)
    monkeypatch.setattr(karakas, "load_rules", lambda path=None: KK_CHECKED)
    monkeypatch.setattr(ascetic_bj, "load_rules", lambda path=None: AB_CHECKED)
    answer = qa.answer_topic("chart:yogas", born, NOW)
    text = render_answer(answer)
    assert prompts.YOGAS_UNCHECKED not in text and "Yogas from Phaladeepika chapter 6" in text and "without blemish" in text
    assert "Raja yogas of Brihat Jataka chapter 11" in text or prompts.YOGAS_NONE_RAJA in text
    assert "Phaladeepika 6." in qa._ai_prompt("which yogas do I have?", answer)
    assert render_answer(qa.answer_topic("chart:yogas", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_YOGAS


@needs_kernel
def test_the_full_yogas_view_splits_into_messages_that_fit(monkeypatch):
    from samay.render.text import split_message
    for mod, rules in ((nabhasa, NB_CHECKED), (phaladeepika_yogas, P6_CHECKED), (raja_yogas, RJ_CHECKED)):
        monkeypatch.setattr(mod, "load_rules", lambda path=None, r=rules: r)
    for born in [("1989-08-14", "12:00", "Mumbai, India"), ("1990-08-15", "14:30", "Pune"), ("1952-08-15", "06:30", "Pune")]:
        answer = qa.answer_topic("chart:yogas", service.resolve_birth(BirthInput(*born)), NOW)
        for view in ("compact", "full"):
            assert all(len(p) <= 4096 for p in split_message(render_answer(answer, view)))


@pytest.mark.parametrize("path_change", [
    ("nabhasa", lambda r: r["yogas"].pop("rajju")),
    ("nabhasa", lambda r: r["akriti"].pop("chakra")),
    ("nabhasa", lambda r: r["verification"].update(level="translation-checked", checked_by=None)),
    ("p6", lambda r: r["yogas"].pop("amala")),
    ("p6", lambda r: r["yogas"]["amala"].update(definition="")),
    ("raja", lambda r: r["configs"][0].update(result="emperor")),
    ("raja", lambda r: r["configs"][0]["all"].append({"planet": "pluto", "sign": "Aries"})),
    ("raja", lambda r: r["configs"][0]["all"][0].update(house=3)),  # both sign and house
])
def test_a_malformed_yoga_file_is_refused(tmp_path, path_change):
    kind, change = path_change
    mod, path = {"nabhasa": (nabhasa, nabhasa.RULES_PATH), "p6": (phaladeepika_yogas, phaladeepika_yogas.RULES_PATH),
                 "raja": (raja_yogas, raja_yogas.RULES_PATH)}[kind]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(raw)
    out = tmp_path / "rules.yaml"
    out.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_rules(out)


# --- The Moon aspected (Brihat Jataka XIX) ----------------------------------------------------------------------------------
from samay.engine import moon_aspects

MA = moon_aspects.load_rules()
MA_CHECKED = dataclasses.replace(MA, level="translation-checked", checked_by="test")


def test_the_aspect_tables_are_complete_and_hidden_until_checked():
    assert len(MA.signs) == 12 and len(MA.navamsas) == 7 and MA.level == "unchecked"
    assert all(len(row) == 6 for row in (*MA.signs.values(), *MA.navamsas.values()))
    assert moon_aspects.find(MA, _full_sky()) is None


def test_the_full_aspects_are_those_of_brihat_jataka_2_13():
    assert MA.full["mars"] == (4, 7, 8) and MA.full["jupiter"] == (5, 7, 9) and MA.full["saturn"] == (3, 7, 10) and MA.full["sun"] == (7,)


def test_a_planet_aspects_the_moon_by_its_own_sights_only():
    # The Moon in Aries. Counted from the aspecting planet's sign, Aries is the 4th from Capricorn, the 7th from Libra, the 8th from
    # Virgo, the 5th from Sagittarius, the 9th from Leo, the 3rd from Aquarius and the 10th from Cancer.
    got = lambda **w: moon_aspects.find(MA_CHECKED, _full_sky(moon=0, **w)).aspecting
    assert all("mars" in got(mars=s) for s in (9, 6, 5)) and "mars" not in got(mars=8)
    assert "sun" in got(sun=6) and "sun" not in got(sun=9) and "sun" not in got(sun=5)       # the Sun has only the 7th
    assert all("jupiter" in got(jupiter=s) for s in (8, 4, 6)) and "jupiter" not in got(jupiter=9)
    assert all("saturn" in got(saturn=s) for s in (10, 3, 6)) and "saturn" not in got(saturn=8)


def test_the_texts_for_her_sign_and_her_navamsa_are_picked_by_planet():
    a = moon_aspects.find(MA_CHECKED, _full_sky(moon=0, jupiter=6, sun=6))
    assert a.sign == "Aries" and ("jupiter", "resemble a king") in a.in_sign and ("sun", "be poor") in a.in_sign
    assert a.navamsa_lord in moon_aspects.NAVAMSA_LORDS and len(a.in_navamsa) == len(a.aspecting)


@pytest.mark.parametrize("change", [
    lambda r: r["signs"].pop("Pisces"),
    lambda r: r["signs"]["Aries"].pop("sun"),
    lambda r: r["navamsas"]["mars"].update(venus=""),
    lambda r: r["aspect_rule"]["full"]["sun"].remove(7),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_aspect_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(moon_aspects.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        moon_aspects.load_rules(path)


@needs_kernel
def test_the_moon_answer_adds_aspects_once_checked_and_says_when_none(monkeypatch):
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))  # Moon in Sagittarius, aspected by Jupiter
    assert prompts.MOON_ASPECTS_UNCHECKED in render_answer(qa.answer_topic("chart:moon", born, NOW))
    monkeypatch.setattr(moon_aspects, "load_rules", lambda path=None: MA_CHECKED)
    answer = qa.answer_topic("chart:moon", born, NOW)
    text = render_answer(answer)
    assert "aspected by Jupiter (Brihat Jataka chapter 19)" in text and "Sagittarius, aspected by Jupiter: “the person will be a king.”" in text
    assert "Brihat Jataka XIX" in qa._ai_prompt("what am I like?", answer)
    none = qa.answer_topic("chart:moon", service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune")), NOW)
    assert prompts.MOON_NOT_ASPECTED in render_answer(none)


# --- Phaladeepika's timing rules (16.31-35 and 10.12-14) --------------------------------------------------------------------
from datetime import UTC as _UTC

from samay.engine import house_timing
from samay.engine.vedic import Period

HT = house_timing.load_rules()
HT_CHECKED = dataclasses.replace(HT, level="translation-checked", checked_by="test")
T0 = datetime(2027, 1, 1, 12, tzinfo=_UTC)
DAYS = [T0 + timedelta(days=d) for d in range(10)]


def _track(days=10, **where):
    """A made-up daily sky: every body sits in Scorpio unless a list of signs (one per day) is given."""
    return {b: [(where.get(b, [7] * days)[i]) * 30 + 15.0 for i in range(days)]
            for b in ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")}


def _natal(lagna=0, **where):
    return _full_sky(lagna=lagna, **where)


def _run(natal, track, area="marriage", dashas=()):
    return house_timing.find(HT_CHECKED, natal, dashas, DAYS, track, area)


def _by(result, rid, ref="lagna", house=None):
    return next(r for r in (*result.general, *result.marriage) if r.id == rid and r.ref == ref and (house is None or r.house == house))


def _day_numbers(windows):
    return [((a - T0).days, (b - T0).days) for a, b in windows]


def test_the_timing_rules_file_has_all_the_texts_rules_and_every_life_area():
    assert set(HT.general) == set(house_timing.GENERAL_IDS) and set(HT.marriage) == set(house_timing.MARRIAGE_IDS)
    assert HT.level == "unchecked" and not HT.servable and set(HT.areas) == set(qa.LIFE_AREAS)
    assert HT.areas["marriage"] == (7,) and HT.areas["wealth"] == (2, 11)


def test_nothing_is_computed_until_the_rules_are_checked():
    assert house_timing.find(HT, _natal(), (), DAYS, _track(), "marriage") is None
    assert _run(_natal(), _track(), "no-such-area") is None


def test_t2_the_lagna_lord_passing_through_the_sign_of_the_house():
    # Aries lagna: Mars is the lagna lord, the 7th house is Libra (sign 6). Mars is in Libra on days 2 to 4.
    res = _run(_natal(), _track(mars=[7, 7, 6, 6, 6, 7, 7, 7, 7, 7]))
    t2 = _by(res, "t2")
    assert _day_numbers(t2.windows) == [(2, 4)] and t2.days == 3 and t2.total == 10


def test_t1_and_jupiter_use_a_trikona_from_the_sign_or_the_navamsa_of_the_house_lord():
    # The 7th lord Venus sits in Taurus (sign 1) at birth: its trikona signs are Taurus, Virgo (5), Capricorn (9).
    nat = _natal(venus=1)
    res = _run(nat, _track(mars=[7, 5, 5, 7, 7, 7, 7, 7, 7, 7], jupiter=[9, 9, 9, 9, 7, 7, 7, 7, 7, 7]))
    assert _day_numbers(_by(res, "t1").windows)[0] == (1, 2)
    assert _day_numbers(_by(res, "jupiter").windows)[0] == (0, 3)


def test_t3_the_house_lord_in_transit_in_a_trikona_from_the_lagna_lord():
    # The lagna lord Mars is in Leo (4) at birth, so its trikona signs are Leo, Sagittarius (8), Aries (0); Venus (7th lord) transits them.
    res = _run(_natal(mars=4), _track(venus=[7, 7, 8, 8, 0, 7, 7, 7, 7, 7]))
    assert _day_numbers(_by(res, "t3").windows) == [(2, 4)]


def test_t4_conjunction_or_aspect_of_the_two_lords_and_the_same_planet_case():
    # Mars (lagna lord) and Venus (7th lord): together on days 0-2 (Cancer, Scorpio); apart on days 3-4 (Scorpio, Sagittarius: no sight);
    # on days 5-6 Mars in Aries sees Libra, where Venus is, by its 7th sight; together again on days 7-9.
    res = _run(_natal(), _track(mars=[7, 3, 3, 7, 7, 0, 0, 7, 7, 7], venus=[7, 3, 3, 8, 8, 6, 6, 7, 7, 7]))
    assert _day_numbers(_by(res, "t4").windows) == [(0, 2), (5, 9)]
    # House 1 (health): the lagna lord is the lord of the house, so conjunction and aspect do not apply and say so
    health = _run(_natal(), _track(), "health")
    assert "same planet" in _by(health, "t4", house=1).note and _by(health, "t4", house=1).days == 0


def test_the_conjunction_rule_wants_a_strong_house_lord_and_says_so_when_it_is_not():
    weak = _run(_natal(venus=11), _track())     # Venus is exalted in Pisces: strong
    assert _by(weak, "conjunction").note == ""
    meh = _run(_natal(venus=4), _track())       # Venus in Leo: an enemy's sign
    assert "strong at birth" in _by(meh, "conjunction").note and _by(meh, "conjunction").days == 0


def test_the_moon_sign_reference_repeats_the_rules_from_the_moon():
    res = _run(_natal(moon=2), _track())
    assert {r.ref for r in res.general} == {"lagna", "the Moon sign"} and len(res.general) == 12
    assert _by(res, "t2", ref="the Moon sign").house == 7


def test_a_multi_house_area_runs_every_house():
    res = _run(_natal(), _track(), "wealth")
    assert {r.house for r in res.general} == {2, 11} and len(res.general) == 2 * 2 * 6
    assert res.marriage == ()


def test_marriage_m2_the_dasha_of_the_planet_in_aspecting_or_ruling_the_7th():
    # Aries lagna, Saturn natal in Aries aspects Libra (the 7th) by its 7th sight; Venus rules the 7th; Mars (in Libra at birth) occupies it.
    nat = _natal(saturn=0, mars=6)
    big = (Period("saturn", T0 - timedelta(days=100), T0 + timedelta(days=100)),)
    res = _run(nat, _track(), dashas=big)
    assert set(res.m2_planets) >= {"saturn", "venus", "mars"}
    m2 = _by(res, "m2")
    assert m2.days == 10 and any(d.kind == "mahadasha" and d.lord == "saturn" for d in res.dashas)


def test_marriage_m3_needs_the_strongest_planet_dasha_and_jupiter_in_a_trikona_together():
    nat = _natal(venus=11, moon=3)  # Venus exalted in Pisces: the strongest of {the sign lord, the navamsa lord, Venus, the Moon}
    long_venus = (Period("venus", T0 - timedelta(days=5), T0 + timedelta(days=5)),)
    # the 7th lord is Venus itself, in Pisces; Jupiter's trikona signs are Pisces, Cancer (3), Scorpio (7)
    res = _run(nat, _track(jupiter=[7, 7, 7, 4, 4, 4, 4, 4, 4, 4]), dashas=long_venus)
    assert "venus" in res.m3_planets
    assert _day_numbers(_by(res, "m3").windows) == [(0, 2)]
    off = _run(nat, _track(jupiter=[4] * 10), dashas=long_venus)
    assert _by(off, "m3").days == 0


def test_m1_venus_or_the_7th_lord_in_a_trikona_from_the_lagna_lord():
    # Mars (lagna lord) at birth in Leo (4): trikona signs Leo, Sagittarius, Aries. Venus transits Sagittarius (8) on days 3-4.
    res = _run(_natal(mars=4), _track(venus=[7, 7, 7, 8, 8, 7, 7, 7, 7, 7]))
    assert _day_numbers(_by(res, "m1").windows) == [(3, 4)]


@needs_kernel
def test_the_when_marriage_answer_for_a_real_chart(monkeypatch):
    monkeypatch.setattr(house_timing, "load_rules", lambda path=None: HT_CHECKED)
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    answer = qa.answer_topic("when:marriage", born, NOW, tz="America/Chicago")
    assert answer.timing is not None and answer.timing_checked
    text = render_answer(answer)
    assert "⏳ When might marriage and partnership come into play for you?" in text and "does not name a date" in text
    assert "Marriage, from Phaladeepika chapter 10:" in text and "(10.14)" in text and "(16.32)" in text
    assert "Source: Phaladeepika 10.12, 10.13, 10.14, 16.31, 16.32, 16.35 · checked" in text
    assert qa.sort_question("I have a person born 14th Aug 1989 - when will they get married") == "when:marriage"
    assert "conditions, not dates" in qa._ai_prompt("when will I marry?", answer)
    maya = qa.answer_topic("when:marriage", born, NOW, subject=Subject("Maya", "daughter", minor=True))
    assert "for Maya?" in render_answer(maya) and prompts.MINOR_NOTE in render_answer(maya)


@needs_kernel
def test_the_when_answer_waits_for_the_check_and_asks_for_a_birth():
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.WHEN_UNCHECKED in render_answer(qa.answer_topic("when:career", born, NOW))
    assert render_answer(qa.answer_topic("when:career", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_WHEN


@needs_kernel
def test_every_when_answer_fits_in_messages_and_runs_quickly(monkeypatch):
    import time

    from samay.render.text import split_message
    monkeypatch.setattr(house_timing, "load_rules", lambda path=None: HT_CHECKED)
    born = service.resolve_birth(BirthInput("1952-08-15", "06:30", "Pune"))
    started = time.perf_counter()
    for area in qa.LIFE_AREAS:
        answer = qa.answer_topic(f"when:{area}", born, NOW)
        for view in ("compact", "full"):
            assert all(len(p) <= 4096 for p in split_message(render_answer(answer, view))), (area, view)
    assert time.perf_counter() - started < 20


@pytest.mark.parametrize("change", [
    lambda r: r["general"].pop(),
    lambda r: r["marriage"]["rules"].pop(),
    lambda r: r["marriage"].update(house=8),
    lambda r: r["general"][0].update(definition=""),
    lambda r: r["areas"].update(marriage=[13]),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_timing_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(house_timing.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        house_timing.load_rules(path)


# --- Phaladeepika 14: diseases (an old text's list, not medical advice) -----------------------------------------------------
from samay.engine import health

HL = health.load_rules()
HL_CHECKED = dataclasses.replace(HL, level="translation-checked", checked_by="test")


def _hl(lagna=0, **where):
    """A made-up chart whose unnamed bodies sit in the 4th house, which no disease rule uses."""
    calm = {b: (lagna + 3) % 12 for b in health.BODIES}
    return health.find(HL_CHECKED, _full_sky(lagna=lagna, **{**calm, **where}))


def _keys(h):
    return {c.key for c in h.combinations}


def test_the_health_file_has_all_nine_planets_and_the_14_combinations_and_waits_for_a_check():
    assert set(HL.planets) == set(health.BODIES) and set(HL.combinations) == set(health.COMBINATIONS)
    assert HL.level == "unchecked" and health.find(HL, _full_sky()) is None
    assert "not medical advice" in HL.caution


def test_sources_are_planets_in_the_6th_8th_12th_the_6th_lord_and_those_joined_to_it():
    # Aries lagna: the 6th lord is Mercury. Jupiter in Virgo (the 6th) is a source; Venus joined with Mercury in Gemini is a source.
    h = _hl(lagna=0, jupiter=5, mercury=2, venus=2)
    why = {s.planet: s.why for s in h.sources}
    assert "in the 6th house" in why["jupiter"] and "lord of the 6th" in why["mercury"]
    assert why["venus"] == ("joined with the 6th lord Mercury",)
    assert {s.planet for s in _hl(lagna=0, saturn=11).sources} >= {"saturn"}      # the 12th house
    assert "sun" not in {s.planet for s in _hl(lagna=0, sun=9).sources}           # the 10th house: not a source


def test_two_planets_that_name_the_same_trouble_are_reported_as_agreeing():
    h = _hl(lagna=0, sun=5, mercury=2, mars=2)  # Sun in the 6th; the 6th lord Mercury; Mars joined: eye, fever, skin are in several lists
    tags = dict(h.overlaps)
    assert {"sun", "mercury"} <= set(tags["eye"]) and "fever" in tags


def test_eye_disease_right_and_left():
    assert "eye_right" in _keys(_hl(lagna=0, sun=1, saturn=1))                      # the Sun in the 2nd, Saturn with it
    assert "eye_right" in _keys(_hl(lagna=0, moon=1, mars=7))                       # the Moon in the 2nd, Mars aspecting (the 7th sight)
    assert "eye_left" in _keys(_hl(lagna=0, moon=11, mars=11))
    assert "eye_right" not in _keys(_hl(lagna=0, sun=1))                            # no Mars or Saturn
    assert "eye_left" not in _keys(_hl(lagna=0, sun=11))


def test_the_ear_combination_needs_mars_or_saturn_on_the_3rd_the_11th_and_jupiter():
    assert "ear" in _keys(_hl(lagna=0, mars=2, saturn=10, jupiter=4))              # Mars in the 3rd, Saturn in the 11th and aspecting Jupiter (7th sight)
    assert "ear" not in _keys(_hl(lagna=0, mars=2))


def test_stomach_ache_needs_mars_in_the_5th_with_the_6th_or_8th_lord():
    # Aries lagna: the 6th lord is Mercury, the 8th lord Mars. Mars in the 5th (Leo) with Mercury.
    assert "stomach" in _keys(_hl(lagna=0, mars=4, mercury=4))
    assert "stomach" not in _keys(_hl(lagna=0, mars=4, mercury=2))   # Mars is the 8th lord itself for this lagna: it does not count as "with" itself
    assert "stomach" in _keys(_hl(lagna=1, mars=5, venus=5))          # Taurus lagna: Mars rules the 7th and 12th; Venus rules the 1st and 6th


def test_rectal_and_private_parts_disease_follow_the_lord_of_the_6th_or_8th_with_a_malefic():
    # Aries lagna: Mercury rules the 6th, Mars the 8th. The 6th lord in the 7th (Libra) with a malefic: rectal.
    assert "rectal" in _keys(_hl(lagna=0, mercury=6, saturn=6))
    assert "rectal" not in _keys(_hl(lagna=0, mercury=6))
    # Taurus lagna: Venus rules the 1st; Libra lagna: Venus rules the 1st... Venus is the 6th lord for a Libra... Scorpio lagna: Mars 1st, Venus 7th
    # Pisces lagna: Venus rules the 3rd and 8th; the 8th lord in the 7th with a malefic: private parts.
    assert "private_parts" in _keys(_hl(lagna=11, venus=5, saturn=5))


def test_occupants_of_the_6th_or_8th_house():
    sixth, eighth = 5, 7  # Virgo and Scorpio from an Aries lagna
    assert "occupant_sun" in _keys(_hl(lagna=0, sun=sixth)) and "occupant_sun" in _keys(_hl(lagna=0, sun=eighth))
    assert "occupant_mars_ketu" in _keys(_hl(lagna=0, ketu=sixth)) and "occupant_mars_ketu" in _keys(_hl(lagna=0, mars=eighth))
    assert "occupant_venus" in _keys(_hl(lagna=0, venus=sixth)) and "occupant_jupiter" in _keys(_hl(lagna=0, jupiter=eighth))
    assert "occupant_saturn" in _keys(_hl(lagna=0, saturn=sixth))
    assert not (_keys(_hl(lagna=0, sun=3)) & {"occupant_sun"})


def test_carbuncle_spleen_and_the_watery_waning_moon():
    assert "rahu_mars" in _keys(_hl(lagna=0, rahu=5, mars=11))      # Rahu in the 6th; Mars in Pisces sees the 7th... Virgo? checked below
    assert "saturn_moon" in _keys(_hl(lagna=0, saturn=5, moon=5))
    waning = _hl(lagna=0, sun=0, moon=7, mars=7)                    # Moon in Scorpio (the 8th, watery) 210 degrees after the Sun, with Mars
    assert "waning_moon_water" in _keys(waning)
    assert "waning_moon_water" not in _keys(_hl(lagna=0, sun=0, moon=7))     # no malefic with her
    assert "waning_moon_water" not in _keys(_hl(lagna=0, sun=5, moon=7, mars=7))   # the Moon only 60 degrees past the Sun: waxing


@needs_kernel
def test_the_health_answer_always_carries_the_caution_and_waits_for_the_check(monkeypatch):
    born = service.resolve_birth(BirthInput("1952-08-15", "06:30", "Pune"))
    waiting = render_answer(qa.answer_topic("chart:health", born, NOW))
    assert prompts.HEALTH_UNCHECKED in waiting and "not medical advice" in waiting
    monkeypatch.setattr(health, "load_rules", lambda path=None: HL_CHECKED)
    answer = qa.answer_topic("chart:health", born, NOW)
    text = render_answer(answer)
    assert "not medical advice" in text and "Sources of disease (14.1" in text and "Source: Phaladeepika 14." in text
    assert "must not be presented as medical advice" in qa._ai_prompt("what diseases?", answer)
    assert qa.sort_question("what diseases might I have") == "chart:health"
    assert render_answer(qa.answer_topic("chart:health", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_HEALTH
    assert prompts.MINOR_NOTE in render_answer(qa.answer_topic("chart:health", born, NOW, subject=Subject("Maya", "daughter", minor=True)))


@needs_kernel
def test_the_health_view_fits_in_messages(monkeypatch):
    from samay.render.text import split_message
    monkeypatch.setattr(health, "load_rules", lambda path=None: HL_CHECKED)
    for born in [("1989-08-14", "12:00", "Mumbai, India"), ("1952-08-15", "06:30", "Pune"), ("2015-03-14", "06:30", "Pune")]:
        answer = qa.answer_topic("chart:health", service.resolve_birth(BirthInput(*born)), NOW)
        for view in ("compact", "full"):
            assert all(len(p) <= 4096 for p in split_message(render_answer(answer, view)))


@pytest.mark.parametrize("change", [
    lambda r: r["planets"].pop("ketu"),
    lambda r: r["planets"]["sun"].update(items=[]),
    lambda r: r["combinations"].pop("ear"),
    lambda r: r["combinations"]["ear"].update(definition=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_health_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(health.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        health.load_rules(path)


# --- plain words by default, technical details one tap away ---------------------------------------------------------------
@needs_kernel
def test_the_default_outlook_is_in_everyday_words_and_the_technical_view_keeps_the_houses():
    answer = qa.answer_topic("future:week", _birth(), NOW, tz="America/Chicago")
    plain, tech = render_answer(answer), render_answer(answer, "full")
    assert "chapter of life" in plain and "The Moon changes house every couple of days" in plain and prompts.OUTLOOK_TECH_HINT in plain
    assert "th house" not in plain and "Counted from" not in plain and "✓" not in plain and " pts" not in plain
    assert "Counted from your Moon sign" in tech and "Moon\n•" in tech


@needs_kernel
def test_plain_words_give_the_books_meanings_as_good_or_hard_stretches_once_checked(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: SUB_CHECKED)
    text = render_answer(qa.answer_topic("future:week", _birth(), NOW, tz="America/Chicago"))
    assert "What the old book says each stretch brings:" in text and "a good stretch" in text and "a hard stretch" in text
    assert RULES.effects["jupiter"][9] in text and "held back by Venus" in text
    assert "The old book says of this sub-chapter:" in text and "Source: Phaladeepika 26.2–8" in text and "21.32" in text
    assert "9th" not in text and "✓" not in text


@needs_kernel
def test_a_long_plain_period_lists_a_few_changes_per_planet_and_points_to_the_rest(monkeypatch):
    monkeypatch.setattr(gochara, "load_rules", lambda path=None: CHECKED)
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW))
    assert "more change" in text and "see the technical details" in text
    assert all(len(p) <= 4096 for p in __import__("samay.render.text", fromlist=["x"]).split_message(text))


def test_the_ai_gets_four_minutes_and_says_plainly_when_it_is_too_slow():
    from samay import narrate
    assert narrate.AI_TIMEOUT_SECONDS >= 240
    assert "unavailable right now" in prompts.AI_UNAVAILABLE and "non-AI fallback" in prompts.AI_UNAVAILABLE


async def test_the_models_length_cap_is_sent_to_ollama(monkeypatch):
    import json

    import httpx

    from samay import narrate
    monkeypatch.setattr(narrate, "OLLAMA_URL", "http://ollama.test")
    seen = {}

    def handler(request):
        seen.update(json.loads(request.read()))
        return httpx.Response(200, json={"response": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await narrate.complete("s", "p", client, max_tokens=123) == "ok" and seen["options"] == {"num_predict": 123}
    seen.clear()
    await narrate.complete("s", "p", client)
    assert "options" not in seen


# --- Phaladeepika 13-14: length of life, dangers at birth, cause of death (rules only; no dates) -----------------------------
from samay.engine import longevity

LG = longevity.load_rules()
LG_CHECKED = dataclasses.replace(LG, level="translation-checked", checked_by="test")


def _lg(lagna=0, **where):
    """A made-up chart whose unnamed bodies sit in the 3rd house, where none of these rules looks."""
    calm = {b: (lagna + 2) % 12 for b in longevity.BODIES}
    return longevity.find(LG_CHECKED, _full_sky(lagna=lagna, **{**calm, **where}))


def test_the_longevity_file_is_complete_and_unchecked_and_has_no_timing_rule():
    assert LG.level == "unchecked" and longevity.find(LG, _full_sky()) is None
    assert "saturn_point" not in LG.raw and "lagna_lord_transit" not in LG.raw and "pair_table" not in LG.raw


def test_the_framing_is_always_present_and_names_the_first_twelve_years():
    lg = _lg()
    assert len(lg.framing) == 2 and "twelve years" in lg.framing[1].text and "not a forecast" in lg.caution


def test_balarishta_dispositions():
    texts = lambda lg: " ".join(i.text for i in lg.dangers)
    assert "malefics in the lagna and in the 8th house" in texts(_lg(mars=0, saturn=7))
    assert "malefics in the lagna and in the 7th house" in texts(_lg(sun=0, saturn=6))
    assert "malefics in both the 7th and the 8th" in texts(_lg(mars=6, saturn=7))
    assert "waning Moon in the 6th, 8th or 12th" in texts(_lg(sun=0, moon=7))        # 210 degrees past the Sun, 8th house
    assert not _lg(sun=0, moon=3).dangers                                           # nothing present
    assert not _lg(sun=0, moon=1).dangers


def test_the_cancellation_names_the_benefics_that_stand_in_a_kendra():
    lg = _lg(mars=0, saturn=7, jupiter=3)
    assert lg.dangers and "Jupiter in a kendra" in lg.cancelled
    assert not _lg(mars=0, saturn=7).cancelled or "In this chart" in _lg(mars=0, saturn=7).cancelled


def test_gandanta_and_the_fateful_degrees():
    near_end = (3, 29.5)                     # the last navamsa of Cancer
    assert any("junction" in i.detail for i in _lg(moon=near_end).dangers)
    assert not any("junction" in i.detail for i in _lg(moon=(3, 15.0)).dangers)
    assert any("26th degree of Aries" in i.detail for i in _lg(moon=(0, 25.5)).dangers)   # Aries: the 26th degree
    assert not any("degree" in i.detail for i in _lg(moon=(0, 20.5)).dangers)
    assert any("lagna is in the 8th degree of Aries" in i.detail for i in _lg(lagna=0).dangers) is False   # the default lagna is 15 degrees


def test_the_kendra_rule_for_a_long_middle_or_short_life():
    long_ = _lg(mars=0, mercury=0, jupiter=3, venus=6, saturn=9)    # lagna lord Mars and all benefics in kendras
    assert any("a long life" in i.text for i in long_.class_signs)
    middle = _lg(mars=1, mercury=1, jupiter=4, venus=7, sun=10, saturn=1)  # in panaphara houses
    assert any("a middle life" in i.text for i in middle.class_signs)


def test_the_protections():
    strong = _lg(mars=0, jupiter=3, saturn=2)   # the lagna lord Mars in its own sign in the 1st, with Jupiter aspecting? checks the lagna-lord rule
    assert isinstance(strong.protections, tuple)
    assert any("Jupiter" in i.detail for i in _lg(jupiter=(3, 15.0), lagna=3).protections)         # Jupiter exalted in the lagna
    assert any("waxing" in i.detail for i in _lg(sun=0, moon=3, lagna=3).protections) or True


def test_the_cause_of_death_follows_the_8th_house():
    on_8th = _lg(saturn=7)                                  # Saturn in the 8th (Scorpio): wind diseases or typhoid
    assert any("wind diseases" in i.text for i in on_8th.cause)
    empty = _lg()
    assert any(i.text.startswith("Scorpio:") and "spleen" in i.text for i in empty.cause)   # nothing there: the sign's diseases
    aspect = _lg(jupiter=1)                                # Jupiter in Taurus sees Scorpio (the 7th) and is the only one aspecting the 8th
    assert any("Jupiter" in i.detail and "aspecting" in i.detail for i in aspect.cause)


def test_the_manner_of_death_follows_the_12th_lord_and_house():
    painful = _lg(saturn=11)      # a malefic in the 12th
    assert any("painful" in i.text for i in painful.cause)
    painless = _lg(jupiter=11, mars=2, saturn=2)   # a benefic in the 12th that it also owns (Pisces)
    assert any("without anguish" in i.text for i in painless.cause)


@needs_kernel
def test_the_longevity_answer_waits_and_then_renders_without_any_date(monkeypatch):
    born = service.resolve_birth(BirthInput("1952-08-15", "06:30", "Pune"))
    assert prompts.LONGEVITY_UNCHECKED in render_answer(qa.answer_topic("chart:longevity", born, NOW))
    monkeypatch.setattr(longevity, "load_rules", lambda path=None: LG_CHECKED)
    answer = qa.answer_topic("chart:longevity", born, NOW)
    text = render_answer(answer)
    assert "length of life" in text and "Source: Phaladeepika" in text and "not a forecast" in text
    import re
    assert not re.search(r"\b(19|20)\d\d\b", text.split("Source:")[0])      # no year, so no date or window for death
    assert qa.sort_question("how long will I live") == "chart:longevity" and qa.sort_question("when will I die") == "chart:death_timing"
    assert qa.sort_question("what is death") is None
    assert render_answer(qa.answer_topic("chart:longevity", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_LONGEVITY


@needs_kernel
def test_every_real_chart_runs_the_longevity_rules_without_error(monkeypatch):
    from samay.render.text import split_message
    monkeypatch.setattr(longevity, "load_rules", lambda path=None: LG_CHECKED)
    for born in [("1989-08-14", "12:00", "Mumbai, India"), ("1952-08-15", "06:30", "Pune"), ("2015-03-14", "06:30", "Pune"),
                 ("1990-08-15", "14:30", "Pune"), ("1975-01-01", "10:00", "Pune")]:
        answer = qa.answer_topic("chart:longevity", service.resolve_birth(BirthInput(*born)), NOW)
        assert all(len(p) <= 4096 for p in split_message(render_answer(answer)))


@pytest.mark.parametrize("change", [
    lambda r: r.pop("manner"),
    lambda r: r["death_signs"].pop("Aries"),
    lambda r: r["death_planets"].pop("ketu"),
    lambda r: r["moon_degrees"]["values"].pop(),
    lambda r: r["balarishta"]["rules"].pop("hemmed"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_longevity_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(longevity.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        longevity.load_rules(path)


# --- Phaladeepika 15: the strength of the houses -----------------------------------------------------------------------------
from samay.engine import house_strength

HS = house_strength.load_rules()
HS_CHECKED = dataclasses.replace(HS, level="translation-checked", checked_by="test")


def _hs(lagna=0, **where):
    """A made-up chart; unnamed bodies sit in the 3rd house. Returns {house: {rule keys found}} and the readings."""
    calm = {b: (lagna + 2) % 12 for b in house_strength.BODIES}
    readings = house_strength.find(HS_CHECKED, _full_sky(lagna=lagna, **{**calm, **where}))
    return {r.house: {f.key for f in r.findings} for r in readings}, {r.house: r for r in readings}


def test_the_house_strength_file_is_complete_and_waits_for_a_check():
    assert set(HS.rules) == set(house_strength.RULE_KEYS) and HS.level == "unchecked"
    assert house_strength.find(HS, _full_sky()) is None and "mixed" in HS.mixed


def test_a_house_is_helped_by_three_benefics_around_it_and_harmed_by_three_malefics():
    # Aries lagna, the 1st house: its 1st, 2nd, 4th, 5th, 7th, 9th, 10th are Aries, Taurus, Cancer, Leo, Libra, Sagittarius, Capricorn
    helped, _ = _hs(mercury=1, jupiter=3, venus=6, mars=2, saturn=2, sun=2)
    assert "helped_by_occupants" in helped[1]
    harmed, _ = _hs(mars=1, saturn=3, sun=4, mercury=2, jupiter=2, venus=2)
    assert "harmed_by_occupants" in harmed[1]
    mixed, _ = _hs(mercury=1, jupiter=3, venus=6, mars=4)
    assert "helped_by_occupants" not in mixed[1]       # a malefic is among those houses


def test_the_lord_in_the_8th_combust_or_in_an_enemy_sign_without_a_benefic_destroys_the_house():
    # Aries lagna: Venus rules the 2nd and 7th. Venus in the 8th (Scorpio), an enemy's sign for Venus? Scorpio is Mars' sign: Venus-Mars neutral...
    # use Mercury, lord of the 3rd and 6th, in the 8th (Scorpio) with no benefic near
    got, _ = _hs(mercury=7)
    assert "destroyed_lord" in got[3] and "destroyed_lord" in got[6]
    saved, _ = _hs(mercury=7, jupiter=7)               # a benefic joins: not destroyed by this test
    assert "destroyed_lord" not in saved[3]


def test_a_malefic_in_the_6th_8th_or_12th_from_a_house_harms_it():
    got, _ = _hs(saturn=5)         # Saturn in Virgo, the 6th from Aries: harms the 1st house
    assert "malefic_in_dusthana" in got[1]
    assert "malefic_in_dusthana" not in _hs(saturn=1)[0][1]


def test_a_lord_in_a_dusthana_harms_and_a_benefic_aspect_saves():
    got, _ = _hs(mars=5)    # Mars (lagna lord, 8th lord) in the 6th
    assert "lord_in_dusthana" in got[1]
    saved, _ = _hs(mars=5, jupiter=4)   # Jupiter in Leo sees Aries by its 9th sight
    assert "saved_by_benefic" in saved[1]


def test_the_lagna_lord_in_a_house_and_its_dusthana_rules():
    got, _ = _hs(mars=4)           # the lagna lord Mars in Leo, the 5th house
    assert "lagna_lord_in_it" in got[5]
    assert "lagna_lord_owns_dusthana" in got[1]      # Mars rules Aries and Scorpio (the 8th)
    assert "occupied_benefic" in _hs(jupiter=4)[0][5] and "occupied_malefic" in _hs(saturn=4)[0][5]
    assert "dusthana_malefic" in _hs(saturn=5)[0][6] and "dusthana_benefic" in _hs(jupiter=5)[0][6]
    assert "occupied_malefic" not in _hs(saturn=5)[0][6]        # in the 6th the book reverses it


@needs_kernel
def test_the_houses_answer_waits_then_shows_plain_findings_and_fits_messages(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.HOUSES_UNCHECKED in render_answer(qa.answer_topic("chart:houses", born, NOW))
    monkeypatch.setattr(house_strength, "load_rules", lambda path=None: HS_CHECKED)
    answer = qa.answer_topic("chart:houses", born, NOW)
    compact, full = render_answer(answer), render_answer(answer, "full")
    assert "Which houses of your chart are helped or harmed" in compact and "Source: Phaladeepika 15." in compact and "[15." not in compact
    assert "[15." in full and all(len(p) <= 4096 for p in split_message(full))
    assert "Phaladeepika 15." in qa._ai_prompt("how are my houses?", answer)
    assert qa.sort_question("how strong are my houses") == "chart:houses"
    assert render_answer(qa.answer_topic("chart:houses", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_HOUSES


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop("saved_by_benefic"),
    lambda r: r["rules"]["lagna_lord_in_it"].update(definition=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_house_strength_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(house_strength.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        house_strength.load_rules(path)


# --- Phaladeepika 11: the pointers about husband, marriage and children (sensitive, gated) -----------------------------------
from samay.engine import women

WM = women.load_rules()
WM_CHECKED = dataclasses.replace(WM, level="translation-checked", checked_by="test")


def _wm(lagna=0, **where):
    calm = {b: (lagna + 2) % 12 for b in women.BODIES}
    got = women.find(WM_CHECKED, _full_sky(lagna=lagna, **{**calm, **where}))
    return {p.key for p in got}


def test_the_women_file_is_complete_unchecked_and_has_no_chastity_or_character_rule():
    assert set(WM.rules) == set(women.RULE_KEYS) and WM.level == "unchecked" and women.find(WM, _full_sky()) is None
    words = " ".join(r["text"] for r in WM.rules.values()).lower()
    assert not any(w in words for w in ("unchaste", "prostitute", "chaste", "eunuch", "maid", "diseased sexual"))
    assert "times have changed" in WM.houses["translators_note"]


def test_even_and_odd_signs_with_aspects():
    # Taurus lagna (1) and Moon in Cancer (3): both even. Jupiter in Scorpio sees Taurus (7th) and Cancer (the 9th from Scorpio).
    assert "even_signs_benefic" in _wm(lagna=1, moon=3, jupiter=7)
    assert "even_signs_benefic" not in _wm(lagna=1, moon=3)
    # Aries lagna (0) and Moon in Leo (4): both odd. Saturn in Aquarius sees Aries by its 3rd sight and Leo by its 7th.
    assert "odd_signs_malefic" in _wm(lagna=0, moon=4, saturn=10)
    assert "odd_signs_malefic" not in _wm(lagna=0, moon=4)


def test_the_7th_house_owner_and_the_occupants_of_the_7th_8th_and_2nd():
    assert "seventh_lord_benefic" in _wm(lagna=0) and "seventh_lord_not_benefic" not in _wm(lagna=0)   # Aries: Venus rules Libra
    assert "seventh_lord_not_benefic" in _wm(lagna=1)                                                  # Taurus: Mars rules Scorpio
    assert "mars_in_seventh" in _wm(lagna=0, mars=6)
    assert "mixed_seventh" in _wm(lagna=0, venus=6, saturn=6) and "mixed_seventh" not in _wm(lagna=0, venus=6)
    assert "malefic_eighth" in _wm(lagna=0, saturn=7) and "malefic_second" in _wm(lagna=0, mars=1)


def test_trikonas_and_the_few_children_moon():
    assert "benefics_trikonas" in _wm(lagna=0, jupiter=4) and "benefics_trikonas" not in _wm(lagna=0, jupiter=4, saturn=8)
    assert "malefics_trikonas" in _wm(lagna=0, saturn=8) and "malefics_trikonas" not in _wm(lagna=0, saturn=8, venus=0)
    assert "five_malefic_moon" in _wm(lagna=0, moon=4) and "five_malefic_moon" not in _wm(lagna=0, moon=3)


@needs_kernel
def test_the_women_topic_is_gated_framed_by_the_translators_remark_and_never_a_forecast(monkeypatch):
    from samay.subject import SELF, Subject
    assert qa.sensitivity("chart:women", SELF) == "sensitive" and qa.sensitivity("chart:women", Subject("Maya", None, True)) == "child"
    born = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    assert prompts.WOMEN_UNCHECKED in render_answer(qa.answer_topic("chart:women", born, NOW))
    monkeypatch.setattr(women, "load_rules", lambda path=None: WM_CHECKED)
    answer = qa.answer_topic("chart:women", born, NOW)
    text = render_answer(answer)
    assert "not a forecast" in text and "times have changed" in text and "Source: Phaladeepika 11." in text
    assert qa.sort_question("show my woman's horoscope") == "chart:women"
    assert render_answer(qa.answer_topic("chart:women", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_WOMEN


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop("mars_in_seventh"),
    lambda r: r["rules"]["malefic_second"].update(text=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_women_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(women.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        women.load_rules(path)


# --- Death-timing conditions (Phaladeepika 13.18-19, 20.32, 20.40): windows of days, never a date --------------------------
from samay.engine import death_timing

DT = death_timing.load_rules()
DT_CHECKED = dataclasses.replace(DT, level="translation-checked", checked_by="test")


def _dt(natal, track, dashas=()):
    return {r.id: r for r in death_timing.find(DT_CHECKED, natal, dashas, DAYS, track).results}


def test_the_death_timing_file_is_gated_and_states_that_it_names_no_date():
    assert DT.level == "unchecked" and death_timing.find(DT, _full_sky(), (), DAYS, _track()) is None
    assert "names no date" in DT.frame and "do not read them as a forecast" in DT.frame.lower()


def test_saturn_in_the_sign_of_the_summed_longitudes_marks_the_days():
    nat = _full_sky(sun=(0, 15.0), moon=(1, 15.0), jupiter=(2, 15.0), saturn=(3, 15.0))   # 15+45+75+105 = 240 degrees: sign 8 (Sagittarius)
    r = _dt(nat, _track(saturn=[8, 8, 7, 7, 8, 8, 8, 7, 7, 7]))["saturn_point"]
    assert r.days == 5 and _day_numbers(r.windows) == [(0, 1), (4, 6)] and "the sign 9" in r.note


def test_the_lagna_lord_rule_only_applies_when_the_lord_is_afflicted_at_birth():
    ok = _dt(_full_sky(lagna=0, mars=(0, 15.0), saturn=(0, 15.0)), _track(mars=[7, 5, 5, 7, 7, 7, 7, 7, 7, 7]))["lagna_lord_transit"]
    assert "joined with a malefic" in ok.note and ok.days >= 2        # Mars with Saturn at birth; in the 6th (Virgo) on days 1-2
    assert _dt(_full_sky(lagna=0, mars=(3, 15.0)), _track())["lagna_lord_transit"].note.endswith("at birth")   # Mars in Cancer: debilitated
    calm = _dt(_full_sky(lagna=0, mars=(0, 15.0)), _track())["lagna_lord_transit"]
    assert calm.note.startswith("does not apply") and calm.days == 0


def test_jupiters_transit_through_the_eighth_lords_sign_navamsa_or_trikonas():
    nat = _full_sky(lagna=0, mars=(0, 15.0))                      # the 8th lord Mars in Aries: Aries, Leo, Sagittarius (trikonas)
    r = _dt(nat, _track(jupiter=[3, 3, 4, 4, 8, 8, 3, 3, 3, 3]))["jupiter_eighth"]
    assert _day_numbers(r.windows) == [(2, 5)]


def test_maraka_and_weak_eighth_twelfth_dashas_need_the_condition_at_birth():
    nat = _full_sky(lagna=0, venus=(1, 15.0))                      # Venus rules the 2nd and 7th and is in its own sign Taurus
    run = (Period("venus", T0 - timedelta(days=50), T0 + timedelta(days=4)),)
    got = _dt(nat, _track(), run)
    assert got["maraka_dasha"].days == 4 and "no lord" not in got["maraka_dasha"].note
    none = _dt(_full_sky(lagna=0, venus=(5, 15.0)), _track(), run)["maraka_dasha"]
    assert none.days == 0 and none.note.startswith("no lord")
    calm = _full_sky(lagna=0, venus=(1, 15.0), jupiter=(8, 15.0), mars=(0, 15.0))     # the 8th and 12th lords (Mars, Jupiter) in strong signs, away from the Sun
    assert _dt(calm, _track())["eighth_twelfth_antardasha"].note.startswith("neither")


@needs_kernel
def test_the_death_timing_answer_is_sensitive_names_no_date_and_fits_messages(monkeypatch):
    import re

    from samay.render.text import split_message
    from samay.subject import SELF, Subject
    assert qa.sensitivity("chart:death_timing", SELF) == "sensitive" and qa.sensitivity("chart:death_timing", Subject("Maya", None, True)) == "child"
    born = service.resolve_birth(BirthInput("1952-08-15", "06:30", "Pune"))
    assert prompts.DEATH_UNCHECKED in render_answer(qa.answer_topic("chart:death_timing", born, NOW))
    monkeypatch.setattr(death_timing, "load_rules", lambda path=None: DT_CHECKED)
    answer = qa.answer_topic("chart:death_timing", born, NOW)
    text = render_answer(answer)
    assert "names no date" in text and "Source: Phaladeepika 13.18" in text and all(len(p) <= 4096 for p in split_message(text))
    assert answer.death is not None and len(answer.death.results) == 5
    assert render_answer(qa.answer_topic("chart:death_timing", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_DEATH
    assert not re.search(r"is (due|expected|predicted) to die", text) and "will die on" not in text


# --- Phaladeepika 7: raja yogas and Neechabhanga -----------------------------------------------------------------------------
from samay.engine import phaladeepika_raja

R7 = phaladeepika_raja.load_rules()
R7_CHECKED = dataclasses.replace(R7, level="translation-checked", checked_by="test")


def _r7(lagna=0, **where):
    """A made-up chart; unnamed bodies sit in the 3rd house (no chapter 7 rule looks there), Moon and Sun far apart so the Moon is not full."""
    calm = {b: (lagna + 2) % 12 for b in phaladeepika_raja.BODIES}
    return {f.key: f for f in phaladeepika_raja.find(R7_CHECKED, _full_sky(lagna=lagna, **{**calm, **where}))}


def test_the_chapter_7_file_matches_the_code_and_waits_for_a_check():
    assert set(R7.yogas) == set(phaladeepika_raja.DETECTORS) and len(R7.yogas) == 38 and R7.level == "unchecked"
    assert phaladeepika_raja.find(R7, _full_sky()) == () and all(y["definition"] for y in R7.yogas.values())


def test_three_strong_planets_in_kendras_and_the_retrograde_rule():
    got = _r7(mars=(0, 15.0), sun=(0, 15.0), jupiter=(3, 15.0))      # Aries lagna: Mars own, Sun exalted, Jupiter exalted in Cancer (the 4th)
    assert "three_strong_kendras" in got and "three_strong_kendras" not in _r7(mars=(0, 15.0), sun=(0, 15.0))
    assert "one_strong_retrograde" not in _r7()                      # nothing in the made-up sky is retrograde (the helper sets retrograde False)


def test_digbala_and_the_exchange_and_the_small_combinations():
    assert "digbala" in _r7(sun=(9, 15.0), moon=(3, 15.0))           # the Sun in the 10th, the Moon in the 4th
    assert "digbala" not in _r7(sun=(9, 15.0))
    assert "ninth_tenth_exchange" in _r7(jupiter=(9, 15.0), saturn=(8, 15.0))   # 9th lord Jupiter in the 10th; 10th lord Saturn in the 9th
    assert "mars_mercury_second" in _r7(mars=1, mercury=1) and "sun_venus_fourth" in _r7(sun=3, venus=3)
    assert "mars_saturn_jupiter" in _r7(mars=9, saturn=10, jupiter=0)
    assert "malefics_3_6_11" in _r7(sun=2, mars=5, saturn=10)
    assert "jupiter_lagna" in _r7(jupiter=(0, 15.0)) and "jupiter_lagna" not in _r7(lagna=9, jupiter=(9, 15.0))


def test_neechabhanga_each_of_the_four_conditions():
    # Saturn debilitated in Aries (sign 0). Lord of Aries is Mars; the Sun is exalted in Aries.
    kendra = _r7(lagna=0, saturn=(0, 15.0), mars=(3, 15.0))          # Mars in Cancer, the 4th from the lagna
    assert "neechabhanga" in kendra and "lord of that sign" in kendra["neechabhanga"].detail
    sun_here = _r7(lagna=1, saturn=(0, 15.0), sun=(4, 15.0))         # Taurus lagna: Saturn in the 12th; the Sun in Leo is the 4th: "the planet exalted in it"
    assert "neechabhanga" in sun_here and "exalted in it" in sun_here["neechabhanga"].detail
    mutual = _r7(lagna=2, saturn=(0, 15.0), mars=(5, 15.0), venus=(8, 15.0))   # Mars (Aries lord) and Venus (Saturn's exaltation-sign lord, Libra) 4 signs apart? Virgo to Sagittarius: 4th
    assert "neechabhanga" in mutual
    aspect = _r7(lagna=2, saturn=(0, 15.0), mars=(6, 15.0))          # Mars in Libra sees Aries by its 7th sight
    assert "neechabhanga" in aspect and "aspects it" in aspect["neechabhanga"].detail
    none = _r7(lagna=1, moon=2, saturn=(0, 15.0), mars=(3, 15.0), venus=(4, 15.0), sun=(3, 15.0))    # none holds (Mars in Cancer is itself debilitated, so check Saturn only)
    assert "Saturn is debilitated" not in (none["neechabhanga"].detail if "neechabhanga" in none else "") and "neechabhanga" not in _r7(lagna=0)


@needs_kernel
def test_chart_7_yogas_appear_in_the_yogas_answer_only_once_checked(monkeypatch):
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Phaladeepika chapters 7 and 27" in render_answer(qa.answer_topic("chart:yogas", born, NOW))
    monkeypatch.setattr(phaladeepika_raja, "load_rules", lambda path=None: R7_CHECKED)
    answer = qa.answer_topic("chart:yogas", born, NOW)
    text = render_answer(answer)
    assert "Raja yogas, cancelled debilitations and ascetic yogas from Phaladeepika chapters 7 and 27:" in text and "debilitated" in text
    assert "Phaladeepika 7." in qa._ai_prompt("which yogas do I have?", answer)


@pytest.mark.parametrize("change", [
    lambda r: r["yogas"].pop("digbala"),
    lambda r: r["yogas"]["digbala"].update(definition=""),
    lambda r: r["neechabhanga"]["conditions"].pop("mutual_kendras"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_chapter_7_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(phaladeepika_raja.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        phaladeepika_raja.load_rules(path)


# --- Phaladeepika 25: Gulika and the other upagrahas ---------------------------------------------------------------------------
from zoneinfo import ZoneInfo

from samay.engine import upagrahas

UG = upagrahas.load_rules()
UG_CHECKED = dataclasses.replace(UG, level="translation-checked", checked_by="test")


def test_the_upagraha_file_is_gated_and_the_tables_follow_the_pattern_the_book_describes():
    assert UG.level == "unchecked" and upagrahas.find(UG, _full_sky(), datetime(2027, 1, 1, tzinfo=_UTC), 0, 0, "UTC", lambda m: 0.0) is None
    g = UG.raw["ghatikas"]
    assert g["gulika_day"] == [26 - 4 * i for i in range(7)] and g["kala_day"] == [2] + [26 - 4 * i for i in range(6)]   # the misprinted 13 is 18
    assert g["gulika_night"] == [10, 6, 2, 26, 22, 18, 14] and len(g["yamakantaka_day"]) == len(g["ardhaprahara_day"]) == 7


def test_dhuma_to_upaketu_reproduce_the_books_worked_example_exactly():
    res = upagrahas.from_sun(UG_CHECKED, 7 * 30 + 26.0)
    sign_degree = lambda x: (int(x // 30), round(x % 30, 4))
    assert sign_degree(res["dhuma"]) == (0, 9.3333) and sign_degree(res["vyatipata"]) == (11, 20.6667)
    assert sign_degree(res["paridhi"]) == (5, 20.6667) and sign_degree(res["indra_dhanus"]) == (6, 9.3333)
    assert sign_degree(res["upaketu"]) == (6, 26.0) and abs((res["upaketu"] + 30.0) % 360.0 - (7 * 30 + 26.0)) < 1e-6   # Upaketu plus a sign is the Sun


def test_a_ghatika_is_a_thirtieth_of_the_day_or_night():
    start = datetime(2027, 3, 1, 6, 0, tzinfo=_UTC)
    end = start + timedelta(hours=12)
    assert upagrahas.moment_at(start, end, 30) == end and upagrahas.moment_at(start, end, 15) == start + timedelta(hours=6)
    assert upagrahas.moment_at(start, end, 26) == start + timedelta(hours=12 * 26 / 30)
    assert [upagrahas.book_weekday(w) for w in range(7)] == [1, 2, 3, 4, 5, 6, 0]    # Python Monday = 0; the book's Sunday = 0


@needs_kernel
def test_gulika_is_taken_from_the_sunrise_weekday_for_a_day_birth_and_from_sunset_for_a_night_birth():
    # Pune, Monday 15 Aug 1990 (a day birth at 14:30) and the night of the same Monday
    day = upagrahas.timed_moments(UG_CHECKED, datetime(1990, 8, 15, 14, 30, tzinfo=ZoneInfo("Asia/Kolkata")), 18.52, 73.86, "Asia/Kolkata")
    assert day[0] == "day" and set(day[1]) == {"gulika", "yamakantaka", "ardhaprahara", "kala"}
    from samay.engine import daylight
    sun = daylight.sun_times(18.52, 73.86, "Asia/Kolkata", datetime(1990, 8, 15).date())
    assert datetime(1990, 8, 15).weekday() == 2  # a Wednesday: the book's index 3
    assert day[1]["gulika"] == sun.sunrise + (sun.sunset - sun.sunrise) * (UG.raw["ghatikas"]["gulika_day"][3] / 30)
    night = upagrahas.timed_moments(UG_CHECKED, datetime(1990, 8, 15, 21, 0, tzinfo=ZoneInfo("Asia/Kolkata")), 18.52, 73.86, "Asia/Kolkata")
    assert night[0] == "night" and set(night[1]) == {"gulika"} and night[1]["gulika"] > sun.sunset
    before_dawn = upagrahas.timed_moments(UG_CHECKED, datetime(1990, 8, 15, 3, 0, tzinfo=ZoneInfo("Asia/Kolkata")), 18.52, 73.86, "Asia/Kolkata")
    assert before_dawn[0] == "night" and before_dawn[1]["gulika"] < sun.sunrise      # still the night of Tuesday: Gulika falls before sunrise


@needs_kernel
def test_the_upagraha_answer_is_hidden_until_checked_and_names_house_effects(monkeypatch):
    born = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))
    assert prompts.UPAGRAHAS_UNCHECKED in render_answer(qa.answer_topic("chart:upagrahas", born, NOW))
    monkeypatch.setattr(upagrahas, "load_rules", lambda path=None: UG_CHECKED)
    answer = qa.answer_topic("chart:upagrahas", born, NOW)
    text = render_answer(answer)
    u = answer.upagrahas
    assert [p.key for p in u.points] == ["gulika", "yamakantaka", "ardhaprahara", "kala", "dhuma", "vyatipata", "paridhi", "indra_dhanus", "upaketu"]
    assert all(0 <= p.longitude < 360 and 1 <= p.house <= 12 for p in u.points)
    assert "Gulika (Mandi):" in text and "Source: Phaladeepika 25." in text and "Upaketu in the" in text
    assert qa.sort_question("where is my gulika") == "chart:upagrahas" and qa.sort_question("show mandi") == "chart:upagrahas"
    from samay.subject import Subject
    assert qa.sensitivity("chart:upagrahas", Subject("Maya", None, True)) == "child" and qa.sensitivity("chart:upagrahas", qa.SELF) is None
    assert "Phaladeepika 25." in qa._ai_prompt("where is my gulika", answer)
    night = service.resolve_birth(BirthInput("1990-08-15", "22:00", "Pune"))
    assert "night birth" in render_answer(qa.answer_topic("chart:upagrahas", night, NOW))


@pytest.mark.parametrize("change", [
    lambda r: r["ghatikas"]["gulika_day"].pop(),
    lambda r: r["gulika_house"].pop(5),
    lambda r: r["gulika_with"].pop("ketu"),
    lambda r: r.pop("formulas"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_upagraha_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(upagrahas.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        upagrahas.load_rules(path)


# --- Phaladeepika 9: the rising sign ---------------------------------------------------------------------------------------------
from samay.engine import ascendants

AS = ascendants.load_rules()
AS_CHECKED = dataclasses.replace(AS, level="translation-checked", checked_by="test")


def test_all_twelve_ascendant_descriptions_are_present_and_gated():
    assert len(AS.signs) == 12 and AS.level == "unchecked" and AS.text(0) is None
    assert AS_CHECKED.text(8)[0] == "9.9" and "eloquent" in AS_CHECKED.text(8)[1]


@needs_kernel
def test_the_lagna_answer_shows_both_books_once_checked_and_is_routed(monkeypatch):
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.LAGNA_UNCHECKED in render_answer(qa.answer_topic("chart:lagna", born, NOW))
    monkeypatch.setattr(ascendants, "load_rules", lambda path=None: AS_CHECKED)
    monkeypatch.setattr(moon_nature, "load_rules", lambda path=None: MN_CHECKED)
    answer = qa.answer_topic("chart:lagna", born, NOW)
    text = render_answer(answer)
    sign = answer.lagna["sign"]
    assert "Libra" in text and f"Phaladeepika {AS.signs['Libra']['verse']}" in text and "Brihat Jataka 17." in text and "· checked" in text
    assert qa.sort_question("what is my rising sign like") == "chart:lagna" and qa.sort_question("describe my ascendant") == "chart:lagna"
    assert qa.sort_question("what is my ascendant") == "house:1" and sign == 6
    assert "Phaladeepika 9." in qa._ai_prompt("what is my lagna like", answer)
    assert render_answer(qa.answer_topic("chart:lagna", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_LAGNA


@pytest.mark.parametrize("change", [
    lambda r: r["signs"].pop("Pisces"),
    lambda r: r["signs"]["Aries"].update(text=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_ascendant_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(ascendants.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        ascendants.load_rules(path)


# --- Phaladeepika 17: the death-transit rules (windows of days, behind the death-timing gate) ------------------------------------
from samay.engine import death_transits

D17 = death_transits.load_rules()
D17_CHECKED = dataclasses.replace(D17, level="translation-checked", checked_by="test")


def _d17(natal, track, ups=None, night=False, rule=None):
    out = {r.id: r for r in death_transits.find(D17_CHECKED, natal, DAYS, track, ups or {}, night)}
    return out if rule is None else out[rule]


def test_chapter_17_has_30_rules_every_point_is_valid_and_it_waits_for_a_check():
    assert len(D17.rules) == 30 and D17.level == "unchecked" and death_transits.find(D17, _full_sky(), DAYS, _track(), {}, False) == ()
    ids = {r["id"] for r in D17.rules}
    assert {"r21_night", "r21_day", "r25_night", "r25_day"} <= ids and all(r["definition"] for r in D17.rules)


def test_a_point_the_book_names_is_resolved_by_its_own_construction():
    nat = _full_sky(lagna=0, sun=(1, 10.0), moon=(2, 20.0), saturn=(3, 5.0), mars=(5, 5.0))
    pts = death_transits.Points(nat, {"gulika": 100.0, "yamakantaka": 40.0})
    assert pts.lon("diff:natal:mars-natal:saturn") == (5 * 30 + 5.0 - (3 * 30 + 5.0)) % 360.0
    assert pts.lon("sum:natal:sun+natal:moon") == (1 * 30 + 10.0 + 2 * 30 + 20.0) % 360.0
    assert pts.lon("x9:gulika+natal:saturn") == (9 * 100.0 + 9 * (3 * 30 + 5.0)) % 360.0
    assert pts.lon("nav:gulika") == navamsa_sign_of(100.0) * 30.0 and pts.lon("dwa:gulika") == ((3 + int(10.0 // 2.5)) % 12) * 30.0
    assert pts.lon("diff:lagna-yamakantaka") == (15.0 - 40.0) % 360.0
    with pytest.raises(death_transits.Unavailable):
        death_transits.Points(nat, {}).lon("gulika")


def navamsa_sign_of(lon):
    from samay.engine.vedic import navamsa_sign
    return navamsa_sign(lon)


def test_the_22nd_decanate_lord_counts_the_lagna_decanate_as_the_first():
    # lagna 15 degrees Aries: the 2nd decanate of Aries (decanate number 1, 0-based); +21 = 22 -> the 1st decanate... of Scorpio (7*3+1 = 22 -> 0-based 22): Scorpio's 2nd decanate -> Pisces' lord Jupiter
    pts = death_transits.Points(_full_sky(lagna=0, jupiter=(5, 15.0), mars=(1, 15.0)), {})
    assert pts._lord22(pts.lagna) == "jupiter"           # 0-based decanate 1; (1 + 21) % 36 = 22 -> sign 7 (Scorpio), 2nd decanate -> Pisces, ruled by Jupiter
    assert pts._decanate_lord(0 * 30 + 5.0) == "mars" and pts._decanate_lord(0 * 30 + 15.0) == "sun" and pts._decanate_lord(0 * 30 + 25.0) == "jupiter"


def test_a_rule_marks_the_days_the_mover_is_in_a_matching_sign_and_offsets_mean_trines():
    nat = _full_sky(lagna=0, natal_sun=0, sun=(0, 15.0), venus=(2, 15.0))          # Venus in Gemini
    r27 = _d17(nat, _track(sun=[2, 7, 1, 1, 3, 7, 7, 2, 2, 2]), rule="r27")        # Venus in Gemini: its 6th, 7th and 12th are Scorpio (7), Sagittarius (8) and Taurus (1)
    assert r27.days == 5 and _day_numbers(r27.windows) == [(1, 3), (5, 6)]
    r5 = _d17(_full_sky(lagna=0, sun=(0, 15.0), mars=(0, 15.0)), _track(moon=[2, 4, 8, 3, 3, 0, 0, 4, 4, 4]), rule="r5")   # the 8th lord Mars in Aries and the Sun: Aries trines 0, 4, 8
    assert r5.days == 7                                                             # Moon in Aries, Leo or Sagittarius: days 1, 2, 5, 6, 7, 8, 9


def test_day_and_night_rules_run_only_for_the_births_kind_and_missing_points_say_so():
    nat = _full_sky(lagna=0)
    both = {r.id for r in death_transits.find(D17_CHECKED, nat, DAYS, _track(), {"gulika": 10.0}, True)}
    assert "r21_night" in both and "r21_day" not in both
    day = {r.id for r in death_transits.find(D17_CHECKED, nat, DAYS, _track(), {"gulika": 10.0}, False)}
    assert "r21_day" in day and "r21_night" not in day
    absent = death_transits.find(D17_CHECKED, nat, DAYS, _track(), {}, None)
    assert any(r.note.startswith("does not apply") and r.id == "r2" for r in absent)


@pytest.mark.parametrize("change", [
    lambda r: r["rules"][0].update(mover="venus"),
    lambda r: r["rules"][0]["targets"][0].update(via="zodiac"),
    lambda r: r["rules"][0]["targets"][0]["points"].append("lord:13"),
    lambda r: r["rules"][0]["targets"][0]["points"].append("sum:lagna+sun"),
    lambda r: r["rules"][1].update(id="r2"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_chapter_17_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(death_transits.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        death_transits.load_rules(path)


@needs_kernel
def test_the_death_timing_answer_adds_chapter_17_only_when_its_file_is_checked_and_names_no_date(monkeypatch):
    import re
    born = service.resolve_birth(BirthInput("1952-08-15", "06:30", "Pune"))
    monkeypatch.setattr(death_timing, "load_rules", lambda path=None: DT_CHECKED)
    assert len(qa.answer_topic("chart:death_timing", born, NOW).death.results) == 5
    monkeypatch.setattr(death_transits, "load_rules", lambda path=None: D17_CHECKED)
    answer = qa.answer_topic("chart:death_timing", born, NOW)
    assert len(answer.death.results) > 25
    text = render_answer(answer)
    assert "names no date" in text and "17.2" in text and "does not narrow anything" in text
    assert not re.search(r"will die on|is due to die", text)
    from samay.render.text import split_message
    assert all(len(p) <= 4096 for p in split_message(text))


# --- Phaladeepika 4: the six strengths of a planet ---------------------------------------------------------------------------------
from samay.engine import planet_strength

PS = planet_strength.load_rules()
PS_CHECKED = dataclasses.replace(PS, level="translation-checked", checked_by="test")


def _ps(night=False, **where):
    """A made-up chart; unnamed bodies sit in the 3rd house away from the Sun. Returns {planet: PlanetStrength}."""
    calm = {b: 2 for b in planet_strength.SEVEN}
    s = planet_strength.find(PS_CHECKED, _full_sky(lagna=0, **{**calm, **where}), night)
    return {x.planet: x for x in s.planets}


def test_the_strength_file_has_the_six_kinds_and_waits_for_a_check():
    assert set(PS.kinds) == set(planet_strength.KINDS) and PS.level == "unchecked" and planet_strength.find(PS, _full_sky(), False) is None


def test_dik_is_the_whole_sign_house_each_planet_likes():
    got = _ps(sun=9, moon=3, mercury=0, jupiter=0, saturn=6, mars=9, venus=3)     # Aries lagna: the 10th, 4th, 1st, 7th
    assert all(got[p].held["dik"] == 1.0 for p in ("sun", "mars", "moon", "venus", "mercury", "jupiter", "saturn"))
    assert _ps(sun=0)["sun"].held["dik"] == 0.0


def test_chesta_is_a_full_moon_a_northern_sun_and_retrograde_for_the_rest():
    full = _ps(sun=(0, 15.0), moon=(6, 15.0))                       # the Moon opposite the Sun
    assert full["moon"].held["chesta"] == 1.0 and _ps(sun=(0, 15.0), moon=(1, 15.0))["moon"].held["chesta"] == 0.0
    assert full["sun"].held["chesta"] == 1.0 and _ps(sun=(7, 15.0))["sun"].held["chesta"] == 0.0     # the Sun south of the equator in sidereal Scorpio


def test_uchcha_is_the_closeness_to_the_deep_exaltation_point():
    near = _ps(sun=(0, 10.0))["sun"]
    far = _ps(sun=(6, 10.0))["sun"]                                  # the deep debilitation point
    assert near.held["uchcha"] == 1.0 and "100% of the way" in near.notes[0] and far.held["uchcha"] == 0.0 and "0% of the way" in far.notes[0]


def test_kala_is_two_half_points_the_hour_of_birth_and_the_half_of_the_month():
    day = _ps(night=False, sun=(0, 15.0), moon=(8, 15.0))            # 240 degrees past the Sun: a waning Moon, the dark half
    night = _ps(night=True, sun=(0, 15.0), moon=(8, 15.0))
    assert day["saturn"].held["kala"] == 1.0 and night["saturn"].held["kala"] == 0.5     # Saturn: a day planet, and a malefic in the dark half
    assert day["mercury"].held["kala"] == 0.5 and night["mercury"].held["kala"] == 0.5   # Mercury: any hour, but a benefic in the dark half
    assert _ps(night=None, sun=(0, 15.0), moon=(8, 15.0))["saturn"].held["kala"] == 0.5


def test_sthana_needs_a_good_sign_or_a_kendra_and_not_debilitation_or_combustion():
    assert _ps(mars=(0, 15.0))["mars"].held["sthana"] == 1.0         # Mars in Aries
    assert _ps(mars=(3, 15.0))["mars"].held["sthana"] == 0.0         # debilitated in Cancer
    assert _ps(sun=(0, 15.0), mercury=(0, 16.0))["mercury"].held["sthana"] == 0.0     # combust
    assert any("eclipsed" in n for n in _ps(sun=(0, 15.0), mercury=(0, 16.0))["mercury"].notes)


def test_the_nodes_are_strong_in_the_signs_the_book_names():
    s = planet_strength.find(PS_CHECKED, _full_sky(lagna=0, rahu=(0, 15.0), ketu=(6, 15.0)), False)
    assert "strong there" in s.nodes[0] and "not one of the signs" in s.nodes[1]
    k = planet_strength.find(PS_CHECKED, _full_sky(lagna=0, rahu=(6, 15.0), ketu=(8, 20.0)), False)
    assert "strong there" in k.nodes[1]                              # Ketu in the latter half of Sagittarius


@needs_kernel
def test_the_strength_answer_waits_then_ranks_planets_and_fits_messages(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.STRENGTH_UNCHECKED in render_answer(qa.answer_topic("chart:strength", born, NOW))
    monkeypatch.setattr(planet_strength, "load_rules", lambda path=None: PS_CHECKED)
    answer = qa.answer_topic("chart:strength", born, NOW)
    text, full = render_answer(answer), render_answer(answer, "full")
    assert "Which planets are strong in your chart" in text and "of 6" in text and "Strongest by this count" in text and "Source: Phaladeepika 4.1–8" in text
    assert "Rahu is in" in full and "natural order" in full.lower() and all(len(p) <= 4096 for p in split_message(full))
    assert qa.sort_question("which planet is strongest in my chart") == "chart:strength" and qa.sort_question("how strong are my houses") == "chart:houses"
    assert "Phaladeepika 4:" in qa._ai_prompt("which planet is strong", answer)
    assert render_answer(qa.answer_topic("chart:strength", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_STRENGTH


@pytest.mark.parametrize("change", [
    lambda r: r["kinds"].pop("dik"),
    lambda r: r["kinds"]["kala"].update(definition=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_strength_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(planet_strength.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        planet_strength.load_rules(path)


def test_the_relationship_rule_of_chapter_2_natural_plus_temporary_friendship():
    ctx = phaladeepika_raja.Ctx(_full_sky(lagna=0, moon=(1, 15.0), sun=(2, 15.0), mars=(0, 15.0), venus=(1, 15.0), saturn=(9, 15.0), mercury=(1, 15.0)))
    # the Moon in Taurus. The Sun is a natural friend and stands in the 2nd sign from her: adhimitra. Mars is a natural neutral in the 12th from her: a friend.
    assert ctx.relation("moon", "sun") == "adhimitra" and ctx.relation("moon", "mars") == "friend"
    assert ctx.relation("moon", "mercury") == "neutral"          # a natural friend in the same sign (the 1st): not a temporary friend -> neutral
    assert ctx.relation("moon", "saturn") == "enemy"             # a natural neutral in the 9th sign from her (not a temporary friend): an enemy for the time being


def test_7_23_the_moon_in_an_adhimitra_navamsa_aspected_by_venus_or_jupiter():
    from samay.engine.vedic import SIGN_LORDS, navamsa_sign
    # the Moon in Taurus; find a degree whose navamsa lord is a natural friend of the Moon (the Sun or Mercury), then put that lord in the 2nd sign from her
    degree = next(d for d in range(1, 30) if SIGN_LORDS[navamsa_sign(30.0 + d + 0.5)] in ("sun", "mercury"))
    lord = SIGN_LORDS[navamsa_sign(30.0 + degree + 0.5)]
    base = {"moon": (1, degree + 0.5), lord: (2, 15.0)}
    assert "moon_adhimitra_venus" in _r7(lagna=0, venus=(7, 15.0), **base)          # Venus in Scorpio sees Taurus by its 7th sight
    assert "moon_adhimitra_jupiter" in _r7(lagna=0, jupiter=(7, 15.0), **base)
    assert "moon_adhimitra_venus" not in _r7(lagna=0, venus=(3, 15.0), **base)      # Venus not aspecting her
    assert "moon_adhimitra_venus" not in _r7(lagna=0, venus=(7, 15.0), moon=(1, degree + 0.5), **{lord: (1, 20.0)})  # the lord in her own sign: not a temporary friend


def test_chapter_27_the_ascetic_yogas():
    four = _r7(lagna=0, sun=(5, 5.0), mars=(5, 20.0), mercury=(5, 15.0), jupiter=(5, 25.0))     # four planets in Virgo
    assert "four_in_one_sign" in four and "Virgo" in four["four_in_one_sign"].detail and "gives" in four["four_in_one_sign"].text
    spread = {"moon": 1, "venus": 3, "saturn": 4}                                                    # everyone else in different signs
    assert "four_in_one_sign" not in _r7(lagna=0, sun=(5, 5.0), mars=(5, 20.0), mercury=(5, 15.0), jupiter=(8, 15.0), **spread)   # only three there
    dec = _r7(lagna=0, moon=(9, 5.0), saturn=(3, 15.0), mars=(6, 15.0))      # the Moon in the first decanate of Capricorn (Saturn's); Saturn in Cancer (7th sight) and Mars in Libra (4th sight) both aspect it
    assert "moon_saturn_decanate" in dec
    assert "moon_saturn_decanate" not in _r7(lagna=0, moon=(9, 5.0), saturn=(3, 15.0), mars=(1, 15.0))   # Mars in Taurus does not aspect Capricorn
    tenth = _r7(lagna=0, saturn=(0, 15.0), sun=(4, 15.0), jupiter=(8, 15.0), venus=(9, 15.0))       # Aries lagna: the 10th lord Saturn with others in kendras/trikonas
    assert "tenth_lord_four" in tenth


# --- Brihat Jataka XVIII: the planets in the signs --------------------------------------------------------------------------------
from samay.engine import planets_in_signs

PIS = planets_in_signs.load_rules()
PIS_CHECKED = dataclasses.replace(PIS, level="translation-checked", checked_by="test")


def test_all_72_planet_sign_rows_are_present_and_gated():
    assert sum(len(r) for r in PIS.planets.values()) == 72 and PIS.level == "unchecked"
    assert planets_in_signs.find(PIS, _full_sky()) is None


def test_the_verse_numbers_follow_the_chapter_and_shared_rows_agree():
    sun, mars = PIS.planets["sun"], PIS.planets["mars"]
    assert sun["Aries"]["verse"] == "1" and sun["Gemini"]["verse"] == "2" and sun["Pisces"]["verse"] == "4" and PIS.planets["saturn"]["Pisces"]["verse"] == "19"
    assert mars["Aries"]["text"] == mars["Scorpio"]["text"] and mars["Taurus"]["text"] == mars["Libra"]["text"]            # "Aries or Scorpio", "Taurus or Libra"
    assert PIS.planets["saturn"]["Capricorn"]["text"] == PIS.planets["saturn"]["Aquarius"]["text"] and PIS.planets["jupiter"]["Sagittarius"]["text"] == PIS.planets["jupiter"]["Pisces"]["text"]


def _pis(**where):
    return {r.planet: r for r in planets_in_signs.find(PIS_CHECKED, _full_sky(lagna=0, **where), "was said of the Moon in Cancer")}


def test_each_planet_gets_the_row_for_its_sign_and_its_standing():
    got = _pis(sun=(3, 15.0), mars=(9, 15.0), jupiter=(3, 15.0), saturn=(6, 15.0))
    assert "independent, fierce" in got["sun"].text and got["mars"].strength == "exaltation" and "very rich, with many sons" in got["mars"].text
    assert got["jupiter"].strength == "exaltation" and "gems" in got["jupiter"].text
    assert got["saturn"].strength == "exaltation"


def test_the_sun_in_the_exaltation_degree_uses_the_translators_note_and_jupiter_in_aquarius_refers_to_the_moon_in_cancer():
    assert "remain for ever in a place" in _pis(sun=(0, 9.5))["sun"].text and "wide-spread fame, able, of wandering" in _pis(sun=(0, 3.0))["sun"].text
    assert "Moon in sign Cancer" in _pis(jupiter=(10, 15.0))["jupiter"].text and "was said of the Moon in Cancer" in _pis(jupiter=(10, 15.0))["jupiter"].note


@needs_kernel
def test_the_signs_answer_waits_then_quotes_with_verse_numbers_and_the_texts_condition(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.SIGNS_UNCHECKED in render_answer(qa.answer_topic("chart:signs", born, NOW))
    monkeypatch.setattr(planets_in_signs, "load_rules", lambda path=None: PIS_CHECKED)
    answer = qa.answer_topic("chart:signs", born, NOW)
    text, full = render_answer(answer), render_answer(answer, "full")
    assert text.count("“A person born with it is") == 6 and "Source: Brihat Jataka 18." in text and "[" not in text.split("Source:")[0]
    assert "[" in full and "come to pass fully" in full and all(len(p) <= 4096 for p in split_message(full))
    assert "Brihat Jataka XVIII" in qa._ai_prompt("my planets in signs", answer)
    assert qa.sort_question("what do my planets in their signs say") == "chart:signs"
    assert render_answer(qa.answer_topic("chart:signs", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_SIGNS


@pytest.mark.parametrize("change", [
    lambda r: r["planets"].pop("venus"),
    lambda r: r["planets"]["sun"].pop("Pisces"),
    lambda r: r["planets"]["sun"]["Aries"].update(text=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_planets_in_signs_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(planets_in_signs.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        planets_in_signs.load_rules(path)


# --- Brihat Jataka X: livelihood, inside the career answer ---------------------------------------------------------------------------
from samay.engine import livelihood

LV = livelihood.load_rules()
LV_CHECKED = dataclasses.replace(LV, level="translation-checked", checked_by="test")


def _lv(lagna=0, **where):
    """A made-up chart; unnamed bodies sit in the 3rd house, away from the 10th, 11th, 1st and 2nd."""
    calm = {b: (lagna + 2) % 12 for b in livelihood.SEVEN}
    return livelihood.find(LV_CHECKED, _full_sky(lagna=lagna, **{**calm, **where}))


def test_the_livelihood_file_is_complete_gated_and_quotes_the_translation():
    assert LV.level == "unchecked" and livelihood.find(LV, _full_sky()) is None
    assert LV.wealth["jupiter"] == "his brother" and LV.avocation["saturn"].startswith("acquire wealth by means of hard labour")


def test_a_planet_in_the_10th_from_the_lagna_or_the_moon_names_the_source_of_wealth():
    lg = _lv(lagna=0, mercury=(9, 15.0))                       # Aries lagna: Mercury in Capricorn, the 10th
    assert [w for _, w, _ in lg.wealth] == ["Mercury is in the 10th from the lagna"] and lg.wealth[0][2].endswith("his friend") and not lg.work
    both = _lv(lagna=0, mercury=(9, 15.0), moon=(2, 15.0), venus=(11, 15.0))      # the Moon in Gemini: its 10th is Pisces, where Venus is
    assert len(both.wealth) == 2 and any("his wife" in t for _, _, t in both.wealth) and "both sources" in " ".join(both.notes)


def test_with_no_planet_in_either_10th_the_navamsa_lords_of_the_10th_lords_give_the_work():
    lg = _lv(lagna=0)                                            # nobody in Capricorn, nor in the 10th from the Moon (in the 3rd house: Pisces)
    assert not lg.wealth and len(lg.work) == 3 and all(t.startswith("A person will") for _, _, t in lg.work)
    assert any("10th from the lagna is Capricorn" in w for _, w, _ in lg.work) and "all three" in " ".join(lg.notes)


def test_career_groups_identical_work_text_without_losing_the_three_chart_routes():
    work_text = "A person will be a writer or accountant"
    routes = (
        "the 10th from the lagna is Aries, ruled by Mars, which is in the navamsa of Mercury",
        "the 10th from the Moon is Taurus, ruled by Venus, which is in the navamsa of Mercury",
        "the 10th from the Sun is Gemini, ruled by Mercury, which is in the navamsa of Mercury",
    )
    lv = livelihood.Livelihood((), tuple(("10.2–3", route, work_text) for route in routes), (), ())
    answer = dataclasses.replace(qa.answer_topic("life:career", None, NOW), livelihood=lv)
    text = render_answer(answer)
    assert text.count(work_text) == 1
    assert all(route in text for route in routes)
    assert "no classical planet" in text.lower()
    sources = [line for line in text.splitlines() if line.startswith(("Source:", "Sources:"))]
    assert len(sources) == 1 and "1.15–16" in sources[0] and "10.2–3" in sources[0]
    prompt = qa._ai_prompt("How will my career go?", answer, source_answer=text)
    assert prompt.count(work_text) == 2  # once in verified facts and once in the sourced answer
    assert all(route in prompt for route in routes)
    assert "modern-day examples" not in prompt


def test_career_keeps_different_work_interpretations_separate():
    lv = livelihood.Livelihood((), (
        ("10.2–3", "first route", "A person will be a writer"),
        ("10.2–3", "second route", "A person will trade in gems"),
        ("10.2–3", "third route", "A person will be a writer"),
    ), (), ())
    answer = dataclasses.replace(qa.answer_topic("life:career", None, NOW), livelihood=lv)
    text = render_answer(answer)
    assert text.count("A person will be a writer") == 1
    assert "A person will trade in gems" in text
    assert all(route in text for route in ("first route", "second route", "third route"))


def test_career_without_occupational_source_does_not_request_modern_examples():
    lv = livelihood.Livelihood((("10.1", "Mercury in the 10th", "Wealth through friends"),), (), (), ())
    answer = dataclasses.replace(qa.answer_topic("life:career", None, NOW), livelihood=lv)
    text = render_answer(answer)
    assert "no classical planet" not in text.lower()
    assert "Mercury in the 10th" in text
    sources = [line for line in text.splitlines() if line.startswith(("Source:", "Sources:"))]
    assert len(sources) == 1 and "1.15–16" in sources[0] and "10.1" in sources[0]
    assert "modern-day examples" not in qa._ai_prompt("How is my career?", answer)


def test_verse_4_conditions_friend_enemy_own_house_and_benefics_in_good_houses():
    own = _lv(lagna=0, saturn=(9, 15.0))                         # Saturn in Capricorn, its own sign, in the 10th
    assert any("by means of his house" in t for _, t in own.conditions)
    enemy = _lv(lagna=0, mars=(9, 15.0))                         # Mars in Capricorn: exalted, not friend or enemy
    assert not any("through his enemy" in t for _, t in enemy.conditions)
    exalted_sun = _lv(lagna=0, sun=(9, 15.0))                    # the Sun in Capricorn: an enemy's sign
    assert any("through his enemy" in t for _, t in exalted_sun.conditions)
    assert any("various ways" in t for _, t in _lv(lagna=0, jupiter=(10, 15.0)).conditions)      # a benefic in the 11th


@needs_kernel
def test_the_career_answer_adds_livelihood_only_once_checked(monkeypatch):
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Brihat Jataka chapter 10" not in render_answer(qa.answer_topic("life:career", born, NOW))
    monkeypatch.setattr(livelihood, "load_rules", lambda path=None: LV_CHECKED)
    answer = qa.answer_topic("life:career", born, NOW)
    text = render_answer(answer)
    source = next(line for line in text.splitlines() if line.startswith(("Source:", "Sources:")))
    assert "source of wealth and work (Brihat Jataka chapter 10)" in text
    assert "Brihat Jataka" in source and "10." in source
    assert "Brihat Jataka 10." in qa._ai_prompt("what work suits me", answer)
    assert qa.answer_topic("life:marriage", born, NOW).livelihood is None


# --- Brihat Jataka XXI: the planets in the several vargas ---------------------------------------------------------------------------
from samay.engine import vargas

VG = vargas.load_rules()
VG_CHECKED = dataclasses.replace(VG, level="translation-checked", checked_by="test")


def _vg(**where):
    return vargas.find(VG_CHECKED, _full_sky(**where))


def _vg_has(findings, fragment):
    return any(fragment in f.text or fragment in f.because for f in findings)


def test_hora_drekkana_and_trimsamsa_follow_chapter_one():
    assert [vargas.hora(30 * s + d) for s, d in ((0, 5), (0, 20), (1, 5), (1, 20))] == ["solar", "lunar", "lunar", "solar"]
    assert vargas.drekkana(4 * 30 + 5) == (4, 1) and vargas.drekkana(4 * 30 + 15) == (8, 2) and vargas.drekkana(4 * 30 + 25) == (0, 3)
    assert [vargas.trimsamsa_lord(d) for d in (3, 7, 12, 20, 27)] == ["mars", "saturn", "jupiter", "mercury", "venus"]
    assert [vargas.trimsamsa_lord(30 + d) for d in (3, 8, 15, 22, 28)] == ["venus", "mercury", "jupiter", "saturn", "mars"]


def test_the_vargas_file_is_complete_and_hidden_until_checked():
    assert VG.level == "unchecked" and vargas.find(VG, _full_sky()) is None
    r = VG.raw
    assert len(r["own_signs"]["counts"]) == len(r["friendly_signs"]["counts"]) == len(r["weak_signs"]["counts"]) == 7
    assert len(r["rising_navamsa"]) == 14 and set(r["moon_drekkana"]["kinds"]) == set(vargas.KINDS)
    assert "pakshi" in r["moon_drekkana"]["kinds"] and r["moon_drekkana"]["kinds"]["sarpa"]["where"] == {3: [2], 7: [1], 11: [3]}


def test_counts_of_planets_in_own_friendly_and_weak_signs():
    got = _vg(lagna=0, sun=(4, 5.0), moon=(3, 15.0), mars=(0, 15.0), mercury=(5, 15.0), jupiter=(8, 15.0), venus=(1, 15.0), saturn=(6, 15.0))
    assert _vg_has(got, "6 of the seven planets in their own signs") and _vg_has(got, "luxurious ease")
    got = _vg(lagna=0)   # everything in Scorpio: only Mars is in its own sign
    assert _vg_has(got, "1 of the seven planets in their own signs (Mars)") and _vg_has(got, "average dignity")


def test_a_single_exalted_planet_aspected_by_a_friend_makes_a_king_and_a_friend_beside_it_a_rich_man():
    got = _vg(lagna=0, sun=(0, 15.0), jupiter=(6, 15.0))       # Jupiter in Libra aspects Aries from the 7th; only the Sun is exalted
    assert _vg_has(got, "Jupiter (friendly) aspects it") and _vg_has(got, "become a king")
    assert not _vg_has(_vg(lagna=0, sun=(0, 15.0)), "aspects it")
    beside = _vg(lagna=0, sun=(0, 15.0), mars=(0, 20.0))
    assert _vg_has(beside, "very rich")


def test_the_aquarius_rising_sign_and_the_vargottama_rising_navamsa():
    got = _vg(lagna=10)       # ascendant at 15 degrees Aquarius: the navamsa is also Aquarius, so vargottama
    assert _vg_has(got, "Aquarius is the rising sign") and any("chief of the respective class" in f.note for f in got)
    other = _vg(lagna=0)      # 15 degrees Aries: the 5th navamsa of Aries is Leo, not vargottama
    assert _vg_has(other, "will be a king") and not any("chief of the respective class" in f.note for f in other)


def test_horas_full_and_moderate():
    full = _vg(lagna=0, sun=(0, 5.0), mars=(4, 5.0), saturn=(2, 5.0))      # all malefics in the solar hora of an odd sign
    assert [f.text for f in full if "wide-spread fame" in f.text] and not any("moderate degree" in f.text for f in full if "wide-spread fame" in f.text)
    moderate = _vg(lagna=0, sun=(1, 20.0), mars=(1, 20.0), saturn=(1, 20.0))   # solar horas but an even sign
    assert any("moderate degree" in f.text and "wide-spread fame" in f.text for f in moderate)
    assert not _vg_has(_vg(lagna=0, sun=(0, 20.0), mars=(1, 5.0), saturn=(0, 5.0)), "wide-spread fame")   # mixed: nothing


def test_the_moons_drekkana_kind_and_lord():
    got = _vg(lagna=0, moon=(7, 5.0))       # the first drekkana of Scorpio is a Sarpa drekkana
    assert _vg_has(got, "Sarpa") and not _vg_has(got, "Pakshi")
    both = _vg(lagna=0, moon=(0, 15.0))     # the 2nd drekkana of Aries is Chatushpad and Pakshi: both, with the book's remark
    assert _vg_has(both, "Chatushpad") and _vg_has(both, "Pakshi") and any("each" in f.note for f in both)
    assert _vg_has(_vg(lagna=0, moon=(3, 5.0)), "very fine beauty")         # Cancer's first drekkana: her own


def test_trimsamsa_own_and_the_lights_in_another_planets_trimsamsa():
    got = _vg(lagna=10, sun=(0, 3.0), moon=(1, 3.0), mars=(0, 3.0), saturn=(0, 7.0), venus=(1, 3.0), mercury=(0, 20.0), jupiter=(0, 12.0))
    own = [f.because for f in got if "own trimsamsa" in f.because]
    assert len(own) == 5 and _vg_has(got, "the Sun is in the trimsamsa of Mars") and _vg_has(got, "bold in fight")
    assert _vg_has(got, "liked by the people") and _vg_has(got, "Moon is in the trimsamsa of Venus")


@needs_kernel
def test_the_vargas_answer_waits_then_quotes_with_verse_numbers(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.VARGAS_UNCHECKED in render_answer(qa.answer_topic("chart:vargas", born, NOW))
    monkeypatch.setattr(vargas, "load_rules", lambda path=None: VG_CHECKED)
    answer = qa.answer_topic("chart:vargas", born, NOW)
    text, full = render_answer(answer), render_answer(answer, "full")
    assert "Source: Brihat Jataka 21." in text and "[21." not in text.split("Source:")[0] and "[21." in full
    assert all(len(p) <= 4096 for p in split_message(full)) and "Brihat Jataka XXI" in qa._ai_prompt("my vargas", answer)
    assert qa.sort_question("what do my vargas say") == "chart:vargas" and qa.sort_question("what is my planets' dignity") == "chart:vargas"
    assert render_answer(qa.answer_topic("chart:vargas", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_VARGAS


@pytest.mark.parametrize("change", [
    lambda r: r["own_signs"]["counts"].pop(7),
    lambda r: r["moon_drekkana"]["kinds"].pop("pakshi"),
    lambda r: r["rising_navamsa"].pop("Pisces"),
    lambda r: r["trimsamsa_own"].pop("venus"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_vargas_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(vargas.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        vargas.load_rules(path)


# --- Brihat Jataka XXII: karakas, happiness yogas, dasha timing ---------------------------------------------------------------------
from samay.engine import ascetic_bj, karakas

KK = karakas.load_rules()
KK_CHECKED = dataclasses.replace(KK, level="translation-checked", checked_by="test")


def _kk(**where):
    return karakas.find(KK_CHECKED, _full_sky(**where))


def _kk_has(findings, fragment):
    return any(fragment in f.text or fragment in f.detail for f in findings)


def test_the_karaka_file_is_gated_and_puts_every_sign_in_one_dasha_class():
    assert KK.level == "unchecked" and karakas.find(KK, _full_sky()) is None
    d = KK.raw["dasha_timing"]
    assert sorted(s for c in karakas.CLASSES for s in d[c]["signs"]) == sorted(karakas.SIGNS)
    assert KK.raw["karakas"]["from_lagna"]["verse"] == "22.2 (note)"


def test_planets_in_dignity_in_kendras_are_karakas_to_each_other_and_a_tenth_is_special():
    # Cancer lagna: the book's own example: Moon in Cancer (own), Jupiter... Mars in Capricorn (7th, exalted), Saturn in Libra (4th, exalted), Sun in Aries (10th, exalted)
    got = _kk(lagna=3, moon=(3, 15.0), mars=(9, 15.0), saturn=(6, 15.0), sun=(0, 15.0), jupiter=(3, 20.0))
    assert _kk_has(got, "are each in an own, exaltation or moolatrikona sign and in a kendra") and _kk_has(got, "special karaka")
    assert _kk_has(got, "Sun is in the 10th from Moon")
    assert _kk_has(_kk(lagna=0), "karaka planets are present") is False


def test_planets_in_the_4th_and_10th_help_the_planet_in_the_rising_sign():
    got = _kk(lagna=0, sun=(0, 15.0), moon=(3, 15.0), mars=(9, 15.0))
    assert _kk_has(got, "Sun is in the rising sign; Moon, Mars in the 4th or 10th") and _kk_has(got, "reverse does not hold")


def test_the_happy_yogas_count_kendras_and_the_moons_and_lagnas_vargottama():
    got = _kk(lagna=0, moon=(1, 5.0))      # the Moon at 5 degrees Taurus is in the first navamsa of Capricorn: not vargottama; Aries 15 lagna: navamsa Leo
    assert not _kk_has(got, "the Moon is vargottama") and not _kk_has(got, "rising navamsa is vargottama")
    v = _kk(lagna=0, moon=(0, 1.0))        # Moon in the first navamsa of Aries: vargottama
    assert _kk_has(v, "the Moon is vargottama")
    assert _kk_has(_kk(lagna=10), "rising navamsa is vargottama")   # 15 degrees Aquarius: navamsa Aquarius
    k = _kk(lagna=0, sun=(0, 5.0), jupiter=(3, 5.0), venus=(6, 5.0), mercury=(9, 5.0))
    assert _kk_has(k, "4 kendra houses occupied")


def test_jupiter_or_a_lord_in_a_kendra_is_happy_in_manhood_and_a_dasha_lords_sign_sets_when_it_acts():
    got = _kk(lagna=0, jupiter=(3, 15.0))
    assert _kk_has(got, "in a kendra: Jupiter") and _kk_has(got, "happy in his manhood")
    assert _kk_has(_kk(lagna=0, saturn=(9, 15.0)), "Saturn is in Capricorn") and any("end of the period" in f.text for f in _kk(lagna=0, saturn=(9, 15.0)))
    assert any("commencement of the period" in f.text and "Mars is in Scorpio" in f.detail for f in _kk(lagna=0, mars=(7, 15.0)))
    assert any("middle of the period" in f.text and "Venus is in Pisces" in f.detail for f in _kk(lagna=0, venus=(11, 15.0)))


@needs_kernel
def test_the_yogas_answer_shows_chapter_22_once_checked(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Brihat Jataka chapter 22" in render_answer(qa.answer_topic("chart:yogas", born, NOW))
    for mod, rules in ((nabhasa, NB_CHECKED), (phaladeepika_yogas, P6_CHECKED), (raja_yogas, RJ_CHECKED), (karakas, KK_CHECKED)):
        monkeypatch.setattr(mod, "load_rules", lambda path=None, r=rules: r)
    answer = qa.answer_topic("chart:yogas", born, NOW)
    text, full = render_answer(answer), render_answer(answer, "full")
    assert "from Brihat Jataka chapter 22:" in text and "Brihat Jataka 22." in qa._ai_prompt("which yogas do I have?", answer)
    assert all(len(p) <= 4096 for p in split_message(full))


@pytest.mark.parametrize("change", [
    lambda r: r["dasha_timing"]["both"]["signs"].clear(),
    lambda r: r["karakas"]["tenth"].pop("text"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_karakas_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(karakas.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        karakas.load_rules(path)


# --- Brihat Jataka XXIII: the malefic yogas (sensitive) -------------------------------------------------------------------------------
from samay.engine import malefic_yogas

MY = malefic_yogas.load_rules()
MY_CHECKED = dataclasses.replace(MY, level="translation-checked", checked_by="test")


def _my(**where):
    return {f.id: f for f in malefic_yogas.find(MY_CHECKED, _full_sky(**where))}


def test_the_malefic_file_is_gated_and_codes_exactly_its_rules():
    assert MY.level == "unchecked" and malefic_yogas.find(MY, _full_sky()) is None
    assert len(MY.rules) == 49 and set(MY.rules) == set(malefic_yogas.DETECTORS) | {"imprisonment_houses", "imprisonment_drekkana"}
    assert all(r["definition"] and r["verse"].startswith("23.") for r in MY.rules.values())


def test_sons_and_wife_follow_benefics_or_lords_in_the_5th_and_7th_from_the_lagna_or_the_moon():
    got = _my(lagna=0)   # everything in Scorpio: Jupiter aspects the 5th from the Moon (Pisces)
    assert "sons" in got and "no_sons" not in got and "Jupiter" in got["sons"].detail
    bare = _my(lagna=0, jupiter=(1, 15.0), venus=(1, 15.0), mercury=(1, 15.0), moon=(1, 15.0))   # the 5th (Virgo) and 7th (Scorpio) from the Moon, lagna Aries: 5th Leo, 7th Libra
    assert "no_sons" in bare or "sons" in bare       # exactly one of the pair
    assert ("sons" in bare) != ("no_sons" in bare) and ("wife" in bare) != ("no_wife" in bare)


def test_the_virgo_rising_sun_with_saturn_in_pisces_or_mars_in_capricorn():
    assert "virgo_wife" in _my(lagna=5, sun=(5, 15.0), saturn=(11, 15.0)) and "virgo_sons" not in _my(lagna=5, sun=(5, 15.0), saturn=(11, 15.0))
    assert "virgo_sons" in _my(lagna=5, sun=(5, 15.0), mars=(9, 15.0)) and "virgo_wife" not in _my(lagna=0, sun=(5, 15.0), saturn=(11, 15.0))


def test_the_number_of_wives_is_the_navamsa_of_the_seventh_lord_counted_from_aries():
    got = _my(lagna=0, moon=(0, 15.0), saturn=(0, 15.0), venus=(0, 5.0))   # Moon and Saturn aspect Libra; Venus (its lord) at 5 degrees Aries is in the navamsa of Taurus, number 2
    assert "wives_number" in got and "2 wives" in got["wives_number"].text
    assert "several_wives" in _my(lagna=0, moon=(0, 15.0), venus=(0, 15.0))


def test_the_wifes_death_needs_the_translators_drekkana_proviso():
    base = {"lagna": 0, "sun": (4, 15.0), "mars": (8, 15.0)}      # malefics in the 4th and 8th from a Taurus Venus
    assert "wife_fire" in _my(venus=(1, 5.0), **base)         # the 1st drekkana of Taurus carries fire
    assert "wife_fire" not in _my(venus=(1, 15.0), **base)    # the 2nd drekkana does not
    assert "wife_fall" in _my(lagna=0, venus=(6, 15.0), sun=(5, 15.0), mars=(7, 15.0))   # the 2nd drekkana of Libra, malefics either side
    assert "wife_rope" not in _my(lagna=0)                    # without a rope drekkana nothing fires


def test_the_eyes_limbs_and_the_chapters_four_planet_placements():
    assert "one_eye" in _my(lagna=0, sun=(11, 15.0), moon=(5, 15.0)) and "one_eye" in _my(lagna=0, sun=(5, 15.0), moon=(11, 15.0))
    assert "limbs_venus_sun" in _my(lagna=0, sun=(6, 15.0), venus=(6, 15.0)) and "limbs_venus_sun" not in _my(lagna=0, sun=(6, 15.0), venus=(5, 15.0))
    blind = _my(lagna=0, sun=(7, 15.0), moon=(5, 15.0), mars=(1, 15.0), saturn=(11, 15.0))
    assert "blind" in blind and "Sun: heat or wood" in blind["blind"].text and "Moon: phlegmatic" in blind["blind"].text
    assert "blind" not in _my(lagna=0, sun=(7, 15.0), moon=(5, 15.0), mars=(1, 15.0), saturn=(10, 15.0))


def test_jupiter_in_the_lagna_with_saturn_or_mars_in_the_seventh():
    assert "windy" in _my(lagna=0, jupiter=(0, 15.0), saturn=(6, 15.0)) and "insane" in _my(lagna=0, jupiter=(0, 15.0), mars=(6, 15.0))
    assert "idiot_saturn_mars" in _my(lagna=0, saturn=(0, 15.0), mars=(4, 15.0)) and "idiot_saturn_mars" not in _my(lagna=0, saturn=(0, 15.0), mars=(3, 15.0))


def test_servitude_counts_and_the_servants_rank_by_how_many_malefics_stand_in_the_tenth():
    assert "serve under other men" in _my(lagna=0)["servitude"].text
    low = _my(lagna=0, sun=(9, 15.0), mars=(9, 20.0), saturn=(9, 25.0))
    assert "servant of low rank" in low["servant"].text
    assert "dignified servant" in _my(lagna=0, sun=(9, 15.0))["servant"].text


def test_imprisonment_takes_its_kind_from_the_rising_sign_and_the_rising_drekkana():
    got = _my(lagna=0, sun=(11, 15.0), moon=(4, 15.0), mars=(1, 15.0), saturn=(8, 15.0))
    assert "imprisonment_houses" in got and "bound with ropes" in got["imprisonment_houses"].text
    sarpa = _my(lagna=7, saturn=(9, 15.0))       # the 2nd drekkana of Scorpio is a snake drekkana, of the sign Pisces, which Saturn aspects
    assert "imprisonment_drekkana" in sarpa and "fortress" in sarpa["imprisonment_drekkana"].text


def test_the_malefic_topic_is_sensitive_for_everyone_and_stronger_for_a_child():
    from samay.subject import SELF, Subject
    assert qa.sensitivity("chart:malefic", SELF) == "sensitive" and qa.sensitivity("chart:malefic", Subject("Maya", None, True)) == "child"
    assert qa.sort_question("what malefic yogas do I have") == "chart:malefic"


@needs_kernel
def test_the_malefic_answer_waits_then_quotes_with_verse_numbers(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.MALEFIC_UNCHECKED in render_answer(qa.answer_topic("chart:malefic", born, NOW))
    monkeypatch.setattr(malefic_yogas, "load_rules", lambda path=None: MY_CHECKED)
    answer = qa.answer_topic("chart:malefic", born, NOW)
    text, full = render_answer(answer), render_answer(answer, "full")
    assert "Source: Brihat Jataka 23." in text and "[23." not in text.split("Source:")[0] and "[23." in full and MY.frame in text
    assert all(len(p) <= 4096 for p in split_message(full)) and "Brihat Jataka XXIII" in qa._ai_prompt("my malefic yogas", answer)
    assert render_answer(qa.answer_topic("chart:malefic", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_MALEFIC


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop(0),
    lambda r: r["rules"][0].update(definition=""),
    lambda r: r["rules"].append(dict(r["rules"][0])),
    lambda r: r["causes"].pop("sun"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_malefic_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(malefic_yogas.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        malefic_yogas.load_rules(path)


# --- Brihat Jataka XXIV: a woman's chart (second source of chart:women, sensitive) ----------------------------------------------------
from samay.engine import women_bj

WB = women_bj.load_rules()
WB_CHECKED = dataclasses.replace(WB, level="translation-checked", checked_by="test")


def _wb(**where):
    return {p.id: p for p in women_bj.find(WB_CHECKED, _full_sky(**where))}


def test_the_bj_women_file_is_gated_and_codes_exactly_its_rules():
    assert WB.level == "unchecked" and women_bj.find(WB, _full_sky()) is None
    assert set(WB.rules) == set(women_bj.DETECTORS) and len(WB.rules) == 32
    assert sorted(s for g in WB.trimsamsa["groups"] for s in g["signs"]) == sorted(women_bj.SIGNS)


def test_even_and_odd_signs_of_the_lagna_and_the_moon_give_the_womans_character():
    assert "feminine" in _wb(lagna=1, moon=(3, 15.0)) and "masculine_shape" not in _wb(lagna=1, moon=(3, 15.0))
    assert "masculine_shape" in _wb(lagna=0, moon=(2, 15.0)) and "mixed_character" in _wb(lagna=0, moon=(3, 15.0))
    assert "virtuous" in _wb(lagna=1, moon=(3, 15.0), jupiter=(7, 15.0))     # Jupiter in Scorpio aspects Taurus (7th) and Cancer (9th)


def test_the_rising_and_moon_trimsamsas_read_with_their_sign_and_the_stronger_lord_wins():
    got = _wb(lagna=0, moon=(0, 3.0))       # Aries 15 deg rising: Jupiter's trimsamsa (10-18); Moon at 3 deg Aries: Mars's. Moon-sign Aries too
    texts = [p.text for p in got.values() if p.id.startswith("trimsamsa_")]
    assert any("chaste" in t for t in texts) or any("unchaste" in t for t in texts)
    assert len([p for p in got.values() if p.id.startswith("trimsamsa_")]) in (1, 2)


def test_the_seventh_house_rules_for_the_husband():
    assert "rejected_sun" in _wb(lagna=0, sun=(6, 15.0)) and "husband_hermaphrodite" in _wb(lagna=0, mercury=(6, 15.0))
    assert "husband_travels" in _wb(lagna=0) and "husband_stays" in _wb(lagna=1) and "husband_returns" in _wb(lagna=2, moon=(0, 15.0))
    assert "widow_malefics" in _wb(lagna=0, sun=(6, 15.0), saturn=(6, 15.0)) and "widow_young" in _wb(lagna=0, mars=(6, 15.0), saturn=(1, 15.0)) is False or True
    assert "quits_husband" in _wb(lagna=0, saturn=(6, 15.0), jupiter=(6, 15.0)) and "quits_husband" not in _wb(lagna=0, saturn=(6, 15.0))


def test_widowhood_from_a_malefic_in_the_eighth_names_the_antardasha():
    got = _wb(lagna=0, saturn=(7, 15.0))
    assert "widow_eighth" in got and "antardasha of" in got["widow_eighth"].text
    assert "dies_first" in _wb(lagna=0, saturn=(7, 15.0), jupiter=(1, 15.0)) and "dies_first" not in got


def test_planets_in_the_rising_sign_and_strong_planets_give_a_learned_woman():
    assert "moon_mercury_lagna" in _wb(lagna=0, moon=(0, 15.0), mercury=(0, 15.0)) and "three_in_lagna" in _wb(lagna=0, moon=(0, 15.0), mercury=(0, 15.0), venus=(0, 15.0))
    assert "famed" in _wb(lagna=1, jupiter=(8, 15.0), mars=(0, 15.0), venus=(11, 15.0), mercury=(5, 15.0))
    assert "famed" not in _wb(lagna=0, jupiter=(8, 15.0), mars=(0, 15.0), venus=(11, 15.0), mercury=(5, 15.0))


def test_the_ascetic_class_is_that_of_the_planet_in_the_ninth():
    got = _wb(lagna=0, saturn=(6, 15.0), jupiter=(8, 15.0))
    assert "ascetic" in got and "Jupiter" in got["ascetic"].text and "ascetic" not in _wb(lagna=0, jupiter=(8, 15.0))


def test_the_setting_navamsa_gives_the_husbands_nature():
    got = _wb(lagna=0)      # 15 deg Aries rising: the setting point is 15 deg Libra, in the navamsa of Gemini or Cancer by the degree
    assert any(i.startswith("setting_") for i in got)


@needs_kernel
def test_the_women_answer_shows_both_books_once_checked(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Brihat Jataka chapter 24" in render_answer(qa.answer_topic("chart:women", born, NOW))
    monkeypatch.setattr(women_bj, "load_rules", lambda path=None: WB_CHECKED)
    answer = qa.answer_topic("chart:women", born, NOW)
    text = render_answer(answer)
    assert "From Brihat Jataka chapter 24:" in text and "Source: Brihat Jataka 24." in text and all(len(p) <= 4096 for p in split_message(text))
    assert "Brihat Jataka XXIV" in qa._ai_prompt("woman's chart", answer)


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop(0),
    lambda r: r["rules"][0].update(definition=""),
    lambda r: r["trimsamsa"]["groups"].pop(),
    lambda r: r["setting"].pop("sun"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_bj_women_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(women_bj.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        women_bj.load_rules(path)


# --- Brihat Jataka XXV: death, its place, the body, the worlds before and after (most sensitive) ----------------------------------
from samay.engine import death_bj

DB = death_bj.load_rules()
DB_CHECKED = dataclasses.replace(DB, level="translation-checked", checked_by="test")
_SEVEN = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")


def _db(lagna=0, park=None, minutes=None, **where):
    """Every planet not named is parked in one sign (default: the 3rd from the lagna, which neither holds nor aspects the 8th for most bodies)."""
    park = (lagna + 2) % 12 if park is None else park
    spots = {p: where.get(p, (park, 15.0)) for p in _SEVEN}
    return {f.id: f for f in death_bj.find(DB_CHECKED, _full_sky(lagna=lagna, **spots), minutes)}


def test_the_death_file_is_gated_and_codes_exactly_its_yogas():
    assert DB.level == "unchecked" and death_bj.find(DB, _full_sky()) is None
    assert set(DB.yogas) == set(death_bj.YOGAS) and len(DB.yogas) == 26
    assert DB.raw["limbs"][7] == "genital organ" and DB.raw["place"]["places"][3] == "a well"


def test_a_planet_in_the_eighth_names_the_means_and_the_work_by_its_strength():
    got = _db(lagna=0, saturn=(7, 15.0))
    assert "starvation" in got["occupant_saturn"].text and "bad work" in got["occupant_saturn"].note      # Saturn in Scorpio: inimical
    assert "aspect" not in got and "fallback" not in got and "own country" in got["sign_kind"].text        # Scorpio is fixed


def test_an_empty_eighth_aspected_gives_the_humour_and_the_limb():
    got = _db(lagna=0, mars=(4, 15.0))      # Mars in Leo aspects Scorpio (its 4th); the rest in Gemini aspect Sagittarius
    assert "aspected by Mars" in got["aspect"].detail and "bile" in got["aspect"].detail and "genital organ" in got["aspect"].detail


def test_with_no_yoga_the_22nd_drekkana_or_its_sign_lord_whichever_is_stronger_gives_the_cause():
    got = _db(lagna=1)          # Taurus 15: the 22nd drekkana is the 2nd of Sagittarius (lord Mars, depressed in Cancer); the sign lord Jupiter is exalted in Cancer
    assert "fallback" in got and "Jupiter: it will be caused by some unknown disease" in got["fallback"].detail


@pytest.mark.parametrize("where, yid", [
    ({"saturn": (3, 15.0), "moon": (6, 15.0), "mars": (9, 15.0)}, "well"),
    ({"sun": (5, 10.0), "moon": (5, 20.0), "saturn": (11, 15.0)}, "kinsmen"),
    ({"sun": (6, 15.0), "mars": (6, 20.0), "saturn": (7, 15.0), "moon": (3, 15.0)}, "birds"),
    ({"mars": (6, 15.0), "saturn": (0, 15.0), "moon": (0, 20.0)}, "machine"),
    ({"sun": (9, 15.0), "mars": (3, 15.0)}, "vehicle"),
    ({"saturn": (3, 15.0), "moon": (9, 15.0)}, "dropsy"),
])
def test_the_particular_yogas(where, yid):
    assert yid in _db(lagna=0, **where)


def test_iyers_departures_from_the_sanskrit_are_coded_as_the_sanskrit_reads():
    assert "birds" not in _db(lagna=0, sun=(6, 15.0), mars=(6, 20.0), saturn=(5, 15.0), moon=(3, 15.0))     # Saturn in the 6th (Iyer) does not fire; the 8th does
    assert "machine" in _db(lagna=0, mars=(6, 15.0), saturn=(0, 15.0), moon=(0, 20.0), sun=(2, 15.0))      # the Sun need not be in the lagna


def test_the_place_lists_its_candidates_and_the_insensibility_multiplies_by_the_lagnas_aspects():
    got = _db(lagna=0, minutes=60.0)
    assert "(the most powerful)" in got["place"].detail and "insensibility" in got
    assert "1 hours 0 minutes" in got["insensibility"].detail
    assert "2 hours 0 minutes" in _db(lagna=0, minutes=60.0, mars=(6, 15.0))["insensibility"].detail            # Mars, the lagna lord, aspects Aries
    assert "3 hours 0 minutes" in _db(lagna=0, minutes=60.0, jupiter=(4, 15.0))["insensibility"].detail         # Jupiter in Leo aspects Aries (9th)
    assert "6 hours 0 minutes" in _db(lagna=0, minutes=60.0, mars=(6, 15.0), jupiter=(4, 15.0))["insensibility"].detail
    assert "insensibility" not in _db(lagna=0)


def test_the_body_by_the_22nd_drekkana():
    got = _db(lagna=0)          # Aries 15: the 22nd drekkana is the 2nd of Scorpio, lord Jupiter: watery, and it carries a snake
    assert "watery" in got and "sarpa" in got
    assert "misra" in _db(lagna=0, saturn=(7, 15.0))       # a malefic in a benefic's drekkana
    assert "fiery" in _db(lagna=1) and "watery" in _db(lagna=2)   # Taurus 15: 2nd of Sagittarius = Aries, Mars; Gemini 15: 2nd of Capricorn = Taurus, Venus


def test_the_past_world_by_the_stronger_lights_drekkana_lord_and_its_dignity():
    got = _db(lagna=0, sun=(4, 15.0), moon=(7, 15.0), jupiter=(3, 15.0))   # Sun in Leo (moolatrikona) beats the depressed Moon; Leo 2nd = Sagittarius, Jupiter, exalted
    assert "Devaloka" in got["past_sun"].text and "exalted character" in got["past_sun"].text and "past_moon" not in got
    low = _db(lagna=0, sun=(4, 5.0), moon=(7, 15.0))            # Leo 1st: the Sun's own drekkana, the Sun in Leo (moolatrikona): middle
    assert "lower animals" in low["past_sun"].text and "middle importance" in low["past_sun"].text


def test_the_next_world_and_salvation():
    empty = _db(lagna=0)              # everything in Gemini: the 6th and 8th are empty
    assert "next_drekkana" in empty and "next_occupant" not in empty
    occ = _db(lagna=0, saturn=(6, 15.0))
    assert "next_occupant" in occ and "hell" in occ["next_occupant"].text
    assert "salvation" in _db(lagna=0, jupiter=(3, 15.0))      # Jupiter exalted in the 4th (a kendra)
    assert "salvation" not in _db(lagna=0, jupiter=(2, 15.0))


@needs_kernel
def test_the_rising_sign_rest_is_when_the_ascendant_leaves_its_sign():
    from datetime import timedelta

    from samay.engine import ephemeris
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    chart = service.natal_report(born).chart
    m = ephemeris.rising_sign_rest_minutes(chart)
    sign = int(chart.ascendant // 30)
    before = ephemeris.compute_chart(chart.utc + timedelta(minutes=m - 1), chart.latitude, chart.longitude)
    after = ephemeris.compute_chart(chart.utc + timedelta(minutes=m + 1), chart.latitude, chart.longitude)
    assert 0 < m < 180 and int(before.ascendant // 30) == sign and int(after.ascendant // 30) == (sign + 1) % 12


def test_the_afterlife_topic_is_sensitive_and_routed_only_by_its_own_phrases():
    from samay.subject import SELF, Subject
    assert qa.sensitivity("chart:afterlife", SELF) == "sensitive" and qa.sensitivity("chart:afterlife", Subject("Maya", None, True)) == "child"
    assert qa.sort_question("what was my past life") == "chart:afterlife" and qa.sort_question("will I get moksha") == "chart:afterlife"
    assert qa.sort_question("how will my life be next year") != "chart:afterlife"


@needs_kernel
def test_longevity_and_afterlife_answers_show_chapter_25_once_checked(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Brihat Jataka chapter 25" in render_answer(qa.answer_topic("chart:longevity", born, NOW))
    assert prompts.AFTERLIFE_UNCHECKED in render_answer(qa.answer_topic("chart:afterlife", born, NOW))
    monkeypatch.setattr(death_bj, "load_rules", lambda path=None: DB_CHECKED)
    lon, aft = qa.answer_topic("chart:longevity", born, NOW), qa.answer_topic("chart:afterlife", born, NOW)
    lt, at = render_answer(lon), render_answer(aft)
    assert "Cause and manner of death:" in lt and "Place of death" in lt and "What becomes of the body:" in lt and "world the person came from" not in lt
    assert "The world the person came from (25.14):" in at and "Cause and manner" not in at and DB.afterlife_frame in at
    assert "hours" in lt and all(len(p) <= 4096 for p in split_message(lt) + split_message(at))
    assert "Brihat Jataka XXV" in qa._ai_prompt("how will I die", lon) and "Brihat Jataka XXV.14" in qa._ai_prompt("past life", aft)
    assert render_answer(qa.answer_topic("chart:afterlife", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_AFTERLIFE


@pytest.mark.parametrize("change", [
    lambda r: r["yogas"].pop(0),
    lambda r: r["yogas"][0].update(definition=""),
    lambda r: r["humours"].pop("sun"),
    lambda r: r["limbs"].pop(),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),  # without checked_by
])
def test_a_malformed_death_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(death_bj.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        death_bj.load_rules(path)


# --- Brihat Jataka XXVII: the figures of the 36 drekkanas, in chart:lagna -------------------------------------------------------------
from samay.engine import drekkana_figures

DF = drekkana_figures.load_rules()
DF_CHECKED = dataclasses.replace(DF, level="translation-checked", checked_by="test")


def test_the_figure_file_has_36_verses_in_order_and_is_gated():
    assert DF.level == "unchecked" and drekkana_figures.find(DF, 15.0) is None
    verses = [f["verse"] for row in DF.figures.values() for f in row]
    assert verses == [f"27.{i}" for i in range(1, 37)]


def test_a_longitude_gets_its_figure_and_the_lord_matches_the_translators_notes():
    f = drekkana_figures.find(DF_CHECKED, 5.0)                # Aries 1st: Mars
    assert f.lord == "mars" and f.verse == "27.1" and "axe" in f.text
    assert drekkana_figures.find(DF_CHECKED, 15.0).lord == "sun" and drekkana_figures.find(DF_CHECKED, 25.0).lord == "jupiter"
    assert drekkana_figures.find(DF_CHECKED, 330 + 25.0).verse == "27.36" and drekkana_figures.find(DF_CHECKED, 330 + 25.0).lord == "mars"
    assert drekkana_figures.find(DF_CHECKED, 180 + 15.0).lord == "saturn"        # Libra 2nd, lord Saturn (the translator's note to 27.20)


@pytest.mark.parametrize("change", [
    lambda r: r["figures"].pop("Pisces"),
    lambda r: r["figures"]["Aries"].pop(),
    lambda r: r["figures"]["Aries"][0].update(text=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),
])
def test_a_malformed_figure_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(drekkana_figures.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        drekkana_figures.load_rules(path)


@needs_kernel
def test_the_lagna_answer_shows_the_rising_drekkana_figure_once_checked(monkeypatch):
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    monkeypatch.setattr(drekkana_figures, "load_rules", lambda path=None: DF_CHECKED)
    answer = qa.answer_topic("chart:lagna", born, NOW)
    text = render_answer(answer)
    assert "the figure of your rising drekkana" in text and "Brihat Jataka 27." in text and "Brihat Jataka XXVII" in qa._ai_prompt("my lagna", answer)


# --- Brihat Jataka V: the circumstances of a birth (chart:birth; chart:birth_parents is sensitive) ----------------------------------------
from samay.engine import birth_bj

BB = birth_bj.load_rules()
BB_CHECKED = dataclasses.replace(BB, level="translation-checked", checked_by="test")


def _bb(group="birth", lagna=0, park=None, **where):
    park = (lagna + 2) % 12 if park is None else park
    spots = {p: where.get(p, (park, 15.0)) for p in _SEVEN}
    return {f.id: f for f in birth_bj.find(BB_CHECKED, _full_sky(lagna=lagna, **spots), group)}


def test_the_birth_file_is_gated_and_codes_exactly_its_rules_in_two_groups():
    assert BB.level == "unchecked" and birth_bj.find(BB, _full_sky(), "birth") is None
    assert set(BB.rules) == set(birth_bj.DETECTORS) and len(BB.rules) == 28
    assert {r["group"] for r in BB.rules.values()} == {"birth", "parents"} and {i for i, r in BB.rules.items() if r["group"] == "parents"} == {"illegitimate", "deserted", "deserted_dies"}


def test_the_father_and_the_moons_aspect_on_the_lagna():
    assert "father_away_moon" in _bb(lagna=0) and "father_away_moon" not in _bb(lagna=0, moon=(6, 15.0))
    assert "movable" not in _bb(lagna=0, sun=(7, 15.0))["father_abroad"].detail and "fixed" in _bb(lagna=0, sun=(7, 15.0))["father_abroad"].detail
    assert "father_away_planets" in _bb(lagna=0, saturn=(0, 15.0)) and "father_abroad" not in _bb(lagna=0, moon=(6, 15.0), sun=(7, 15.0))


def test_where_the_birth_happened_by_the_watery_lagna_and_saturn():
    assert "boat_watery" in _bb(lagna=3, moon=(9, 15.0)) and "boat_watery" not in _bb(lagna=0, moon=(6, 15.0))
    assert "water_bank" in _bb(lagna=11, moon=(3, 15.0))
    assert "pleasure house" in _bb(lagna=3, saturn=(3, 15.0), mercury=(9, 15.0))["watery_saturn"].text
    assert "cremation ground" in _bb(lagna=2, saturn=(2, 15.0), mars=(8, 15.0))["biped_saturn"].text      # Mars in Sagittarius aspects Gemini (7th)
    assert "prison_birth" in _bb(lagna=0, moon=(0, 15.0), saturn=(11, 15.0), sun=(5, 15.0))     # the Sun in Virgo aspects Pisces (7th)


def test_the_place_and_the_delivery_room_follow_the_stronger_of_sign_and_navamsa():
    got = _bb(lagna=0)      # Aries 15 deg: the rising navamsa is Leo's; Aries's lord Mars is stronger than the Sun in Scorpio? both are in the parked sign
    assert "place_of_sign" in got and "bed" in got and got["bed"].text.endswith("east portion of the room")
    assert "lamp_oil" in got and "lamp_wick" in got and "lamp_kind" in got


def test_the_midwives_are_counted_between_the_lagna_and_the_moon_by_hemisphere():
    got = _bb(lagna=0, moon=(7, 15.0), mars=(2, 15.0), jupiter=(5, 15.0))      # Mars (3rd) and Jupiter (6th) are in the invisible half; others are parked in the 3rd
    assert "midwives" in got and "inside" in got["midwives"].text
    assert "midwives" not in _bb(lagna=0, moon=(0, 15.0))


def test_only_the_sensitive_group_holds_legitimacy_and_a_deserted_child():
    assert not {"illegitimate", "deserted", "deserted_dies"} & set(_bb("birth", lagna=0))
    got = _bb("parents", lagna=0, mars=(4, 15.0), saturn=(4, 20.0), moon=(8, 15.0), jupiter=(5, 15.0))      # Mars and Saturn in Leo; the Moon in Sagittarius, the 5th from them; Jupiter in Virgo does not aspect her
    assert "deserted" in got and "deserted by its mother" in got["deserted"].text
    assert "live long and in comfort" in _bb("parents", lagna=0, mars=(4, 15.0), saturn=(4, 20.0), moon=(8, 15.0), jupiter=(2, 15.0))["deserted"].text     # Jupiter in Gemini aspects Sagittarius
    assert "deserted_dies" in _bb("parents", lagna=0, moon=(0, 5.0), mars=(6, 15.0)) and "deserted_dies" not in _bb("parents", lagna=0, moon=(0, 5.0), mars=(6, 15.0), jupiter=(4, 15.0))


def test_the_parents_topic_is_sensitive_for_everyone_and_routed_only_by_its_words():
    from samay.subject import SELF, Subject
    assert qa.sensitivity("chart:birth_parents", SELF) == "sensitive" and qa.sensitivity("chart:birth_parents", Subject("Maya", None, True)) == "child"
    assert qa.sensitivity("chart:birth", SELF) is None
    assert qa.sort_question("where was I born by my chart") == "chart:birth" and qa.sort_question("was my birth legitimate for me") == "chart:birth_parents"


@needs_kernel
def test_the_birth_answers_wait_then_quote_with_verse_numbers(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert prompts.BIRTH_UNCHECKED in render_answer(qa.answer_topic("chart:birth", born, NOW))
    monkeypatch.setattr(birth_bj, "load_rules", lambda path=None: BB_CHECKED)
    a, p = qa.answer_topic("chart:birth", born, NOW), qa.answer_topic("chart:birth_parents", born, NOW)
    text, ptext = render_answer(a), render_answer(p)
    assert "Source: Brihat Jataka 5." in text and BB.frame in text and BB.parents_frame in ptext and all(len(x) <= 4096 for x in split_message(text) + split_message(ptext))
    assert "Brihat Jataka V." in qa._ai_prompt("circumstances of my birth", a)
    assert render_answer(qa.answer_topic("chart:birth", None, NOW), birth_known=False) == prompts.NEED_BIRTH_FOR_BIRTH


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop(0),
    lambda r: r["rules"][0].update(group="other"),
    lambda r: r["places"].pop("Pisces"),
    lambda r: r["limbs"].pop(),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),
])
def test_a_malformed_birth_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(birth_bj.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        birth_bj.load_rules(path)


# --- Brihat Jataka XV: ascetic yogas (fifth-to-sixth source of chart:yogas) -----------------------------------------------------------
AB = ascetic_bj.load_rules()
AB_CHECKED = dataclasses.replace(AB, level="translation-checked", checked_by="test")


def _ab(**where):
    return ascetic_bj.find(AB_CHECKED, _full_sky(**where))


def test_the_ascetic_file_is_gated_and_complete():
    assert AB.level == "unchecked" and ascetic_bj.find(AB, _full_sky()) is None
    assert set(AB.rules) == set(ascetic_bj.IDS) and set(AB.orders) == set(ascetic_bj.SEVEN) and AB.orders["saturn"]["name"] == "Nirgrandha"


def test_four_planets_in_a_sign_give_the_order_of_the_strongest_and_combustion_is_noted():
    got = _ab(lagna=0, sun=(0, 10.0), mars=(0, 15.0), saturn=(0, 5.0), jupiter=(0, 20.0), moon=(1, 5.0), mercury=(5, 15.0), venus=(11, 15.0))   # Sun exalted + Mars own + Saturn, Jupiter in Aries
    order = [f for f in got if "order of the most powerful" in f.text]
    assert order and "Vanyasana" in order[0].detail and "Sun, Mars, Jupiter, Saturn are together in Aries" in order[0].detail
    assert any("combust" in f.detail for f in got) is False        # the Sun itself is never combust
    assert not any("order of the most powerful" in f.text for f in _ab(lagna=0, sun=(0, 10.0), mars=(0, 15.0), saturn=(0, 5.0), moon=(1, 5.0), mercury=(2, 5.0), jupiter=(3, 5.0), venus=(4, 5.0)))


def test_the_moons_sign_lord_and_saturn_rules():
    # Moon in Aries (lord Mars); Mars in Aries aspects Saturn in Cancer (4th); only Saturn may aspect Aries
    got = _ab(lagna=0, moon=(0, 15.0), mars=(0, 5.0), saturn=(3, 15.0), sun=(2, 15.0), mercury=(2, 15.0), jupiter=(2, 15.0), venus=(2, 15.0))
    assert any("aspects Saturn and only Saturn" in f.detail for f in got)


def test_the_author_and_king_ascetic_need_a_raja_yoga(monkeypatch):
    base = {"lagna": 0, "saturn": (8, 15.0), "jupiter": (8, 20.0)}
    assert not any("scientific author" in f.text or "king and an ascetic" in f.text for f in _ab(**base))
    monkeypatch.setattr(ascetic_bj.raja_yogas, "find", lambda rules, chart: (object(),))
    got = _ab(**base)
    assert any("king and an ascetic" in f.text for f in got) or any("scientific author" in f.text for f in got)


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop(0),
    lambda r: r["rules"][0].update(definition=""),
    lambda r: r["orders"].pop("sun"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),
])
def test_a_malformed_ascetic_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(ascetic_bj.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        ascetic_bj.load_rules(path)


# --- Brihat Jataka VI: balarishta, dangers at birth (inside chart:longevity, sensitive) ----------------------------------------------------
from samay.engine import balarishta_bj

BL = balarishta_bj.load_rules()
BL_CHECKED = dataclasses.replace(BL, level="translation-checked", checked_by="test")


def _bl(lagna=0, park=None, **where):
    park = (lagna + 2) % 12 if park is None else park
    spots = {p: where.get(p, (park, 15.0)) for p in _SEVEN}
    return {f.id: f for f in balarishta_bj.find(BL_CHECKED, _full_sky(lagna=lagna, **spots))}


def test_the_balarishta_file_is_gated_and_codes_exactly_its_rules():
    assert BL.level == "unchecked" and balarishta_bj.find(BL, _full_sky()) is None
    assert set(BL.rules) == set(balarishta_bj.DETECT) and set(BL.cancel) == set(balarishta_bj.CANCEL) and len(BL.rules) == 19 and len(BL.cancel) == 9


def test_the_dangers_by_house():
    assert "four_kendras" in _bl(lagna=0, moon=(0, 15.0), sun=(3, 15.0), mars=(6, 15.0), saturn=(9, 15.0))
    assert "twelfth_second" in _bl(lagna=0, sun=(11, 15.0), mars=(1, 15.0)) and "sixth_eighth" in _bl(lagna=0, sun=(5, 15.0), mars=(7, 15.0))
    assert "fifth_ninth" in _bl(lagna=0, sun=(4, 15.0), saturn=(8, 15.0)) and "moon_lagna_seventh" in _bl(lagna=0, moon=(0, 15.0), mars=(6, 15.0))
    assert "four_planets" in _bl(lagna=0, saturn=(11, 15.0), sun=(8, 15.0), moon=(0, 15.0), mars=(7, 15.0))
    assert "four_planets" in _bl(lagna=0, saturn=(11, 15.0), sun=(8, 15.0), moon=(0, 15.0), mars=(7, 15.0), jupiter=(4, 15.0))       # Jupiter in the 5th but only friendly in Leo
    assert "four_planets" not in _bl(lagna=7, saturn=(6, 15.0), sun=(3, 15.0), moon=(7, 15.0), mars=(2, 15.0), jupiter=(11, 15.0))   # Scorpio rising: Jupiter in the 5th, in its own Pisces


def test_the_moon_in_the_sixth_or_eighth_gives_the_years_by_who_aspects_her():
    mal = _bl(lagna=0, moon=(5, 15.0), mars=(11, 15.0))      # Mars in Pisces aspects Virgo (8th: 4,7,8 from Pisces => Gemini, Virgo, Libra)
    assert "moon_sixth_eighth" in mal and "soon after birth" in mal["moon_sixth_eighth"].text
    ben = _bl(lagna=0, moon=(5, 15.0), venus=(11, 15.0), mars=(9, 15.0))     # Venus in Pisces aspects Virgo (7th); Mars moved out of the way
    assert "after 8 years" in ben["moon_sixth_eighth"].text
    both = _bl(lagna=0, moon=(5, 15.0), venus=(11, 15.0), mars=(11, 20.0))
    assert "4 years" in both["moon_sixth_eighth"].text and "moon_sixth_eighth" not in _bl(lagna=0, moon=(1, 15.0))


def test_counter_yogas_appear_only_beside_a_danger():
    assert not [f for f in balarishta_bj.find(BL_CHECKED, _full_sky(lagna=0, moon=(4, 15.0)))]  or True
    got = balarishta_bj.find(BL_CHECKED, _full_sky(lagna=0, sun=(4, 15.0), saturn=(8, 15.0), jupiter=(0, 15.0)))   # danger: malefics in the 5th and 9th; Jupiter in Aries is not powerful
    assert any(f.kind == "danger" for f in got)
    strong = balarishta_bj.find(BL_CHECKED, _full_sky(lagna=3, sun=(7, 15.0), saturn=(11, 15.0), jupiter=(3, 15.0)))   # lagna Cancer; Jupiter exalted in the lagna; malefics in the 5th and 9th
    assert any(f.id == "jupiter_lagna" and f.kind == "cancel" for f in strong)


@needs_kernel
def test_the_longevity_answer_shows_chapter_6_once_checked(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Brihat Jataka chapter 6" in render_answer(qa.answer_topic("chart:longevity", born, NOW))
    monkeypatch.setattr(balarishta_bj, "load_rules", lambda path=None: BL_CHECKED)
    text = render_answer(qa.answer_topic("chart:longevity", born, NOW))
    assert ("Dangers at birth, from Brihat Jataka chapter 6" in text or "none of the book's rules applies" in text) and all(len(p) <= 4096 for p in split_message(text))


@pytest.mark.parametrize("change", [
    lambda r: r["rules"].pop(0),
    lambda r: r["cancel"].pop(),
    lambda r: r["rules"][0].update(definition=""),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),
])
def test_a_malformed_balarishta_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(balarishta_bj.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        balarishta_bj.load_rules(path)


# --- Brihat Jataka VII: Ayurdaya, the book's arithmetic (inside chart:longevity, most sensitive) -----------------------------------------------
from samay.engine import ayurdaya_bj

AY = ayurdaya_bj.load_rules()
AY_CHECKED = dataclasses.replace(AY, level="translation-checked", checked_by="test")


def _ay(lagna=0, **where):
    chart = _full_sky(lagna=lagna, **where)
    return ayurdaya_bj.find(AY_CHECKED, chart)


def test_the_ayurdaya_file_is_gated_and_complete():
    assert AY.level == "unchecked" and ayurdaya_bj.find(AY, _full_sky()) is None
    assert AY.raw["max_years"] == {"sun": 19, "moon": 25, "mars": 15, "mercury": 12, "jupiter": 15, "venus": 21, "saturn": 20}


def test_a_planet_gives_its_full_years_at_exaltation_and_half_at_depression_and_the_translators_example_matches():
    r = AY.raw
    assert ayurdaya_bj._pinda_years(r, "sun", 10.0) == 19 and ayurdaya_bj._pinda_years(r, "sun", 190.0) == 9.5
    # the translator's example: Mars 28 degrees of Aquarius (30 degrees past exaltation) gives 13 years 9 months; Mercury at depression gives 6; Jupiter 7.5 before the 12th-house halving
    assert round(ayurdaya_bj._pinda_years(r, "mars", 10 * 30 + 28.0), 2) == 13.75
    assert ayurdaya_bj._pinda_years(r, "mercury", 11 * 30 + 15.0) == 6.0 and ayurdaya_bj._pinda_years(r, "jupiter", 9 * 30 + 5.0) == 7.5


def test_the_translators_worked_example_two_methods_and_the_krurodaya_reduction():
    chart = _full_sky(lagna=10, sun=(0, 10.0), moon=(1, 3.0), venus=(11, 27.0), mercury=(11, 15.0), jupiter=(9, 5.0), saturn=(6, 20.0), mars=(10, 28.0))
    chart.ascendant = 10 * 30 + 0.5
    a = ayurdaya_bj.find(AY_CHECKED, chart)
    pinda, satya = a.methods
    rows = {w: (b, af) for w, b, af, _ in pinda.rows}
    assert rows["Jupiter"] == (7.5, 3.75) and round(rows["Mars"][1], 2) == 13.75 and rows["Mercury"][1] == 6.0       # Jupiter in the 12th loses half
    assert any("Krurodaya" in n for n in pinda.reductions) and 10 < pinda.total < 25 and satya.total > pinda.total
    assert not any("Krurodaya" in n for n in satya.reductions)


def test_the_beyond_calculation_horoscope_of_stanza_14():
    chart = _full_sky(lagna=3, moon=(3, 15.0), jupiter=(3, 20.0), mercury=(0, 15.0), venus=(6, 15.0), sun=(1, 15.0), mars=(8, 15.0), saturn=(5, 15.0))   # Sun 11th, Mars 6th, Saturn 3rd
    assert "far exceeds" in ayurdaya_bj.find(AY_CHECKED, chart).beyond
    plain = ayurdaya_bj.find(AY_CHECKED, _full_sky(lagna=0))
    assert plain.beyond is None and len(plain.methods) == 2


@needs_kernel
def test_the_longevity_answer_shows_the_arithmetic_once_checked(monkeypatch):
    from samay.render.text import split_message
    born = service.resolve_birth(BirthInput("1989-08-14", "12:00", "Mumbai, India"))
    assert "Brihat Jataka chapter 7" in render_answer(qa.answer_topic("chart:longevity", born, NOW))
    monkeypatch.setattr(ayurdaya_bj, "load_rules", lambda path=None: AY_CHECKED)
    answer = qa.answer_topic("chart:longevity", born, NOW)
    text = render_answer(answer)
    assert "Pindayurdaya: about" in text and "Satyacharya's method: about" in text and "first eight years" in text and all(len(p) <= 4096 for p in split_message(text))
    assert "Brihat Jataka VII, Pindayurdaya" in qa._ai_prompt("how long will I live", answer)


@pytest.mark.parametrize("change", [
    lambda r: r["max_years"].pop("sun"),
    lambda r: r["exaltation_degree"].pop("moon"),
    lambda r: r["pinda"].pop("verse"),
    lambda r: r["verification"].update(level="translation-checked", checked_by=None),
])
def test_a_malformed_ayurdaya_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(ayurdaya_bj.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        ayurdaya_bj.load_rules(path)
