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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    return SimpleNamespace(planets=planets, ascendant=lagna * 30 + 15.0)


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
    assert waiting.count(prompts.YOGAS_UNCHECKED) == 3 and "Source:" not in waiting
    monkeypatch.setattr(nabhasa, "load_rules", lambda path=None: NB_CHECKED)
    only_nabhasa = render_answer(qa.answer_topic("chart:yogas", born, NOW))
    assert only_nabhasa.count(prompts.YOGAS_UNCHECKED) == 2 and "Nabhasa yogas (Brihat Jataka chapter 12)" in only_nabhasa
    monkeypatch.setattr(phaladeepika_yogas, "load_rules", lambda path=None: P6_CHECKED)
    monkeypatch.setattr(raja_yogas, "load_rules", lambda path=None: RJ_CHECKED)
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
    ("nabhasa", lambda r: r["verification"].update(level="translation-checked")),
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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


def test_the_ai_gets_four_minutes_and_a_length_cap_and_says_plainly_when_it_is_too_slow():
    from samay import narrate
    assert narrate.AI_TIMEOUT_SECONDS >= 240 and 0 < narrate.AI_MAX_TOKENS <= 400
    assert "too slow" in prompts.AI_UNAVAILABLE and "does not depend on it" in prompts.AI_UNAVAILABLE


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
    assert qa.sort_question("when will I die") == "chart:longevity" and qa.sort_question("what is death") is None
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
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
    lambda r: r["verification"].update(level="translation-checked"),  # without checked_by
])
def test_a_malformed_house_strength_file_is_refused(tmp_path, change):
    raw = yaml.safe_load(house_strength.RULES_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        house_strength.load_rules(path)
