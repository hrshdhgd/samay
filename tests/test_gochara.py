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
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW))
    assert prompts.OUTLOOK_DASHA_UNCHECKED in text and "The text:" not in text
    assert not any(t in text for t, _ in SUB.effects.values())


@needs_kernel
def test_checked_antardasha_results_appear_under_their_dasha_lines_with_sources(monkeypatch):
    monkeypatch.setattr(antardasha, "load_rules", lambda path=None: SUB_CHECKED)
    text = render_answer(qa.answer_topic("future:years", _birth(), NOW))
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
    compact, full = render_answer(qa.answer_topic("future:year", _birth(), NOW)), render_answer(
        qa.answer_topic("future:year", _birth(), NOW), "full")
    assert " pts)" in compact and "23.11" in compact and "Brihat Jataka's tables differ" not in compact
    assert "pts: " in full and "Phaladeepika's English translation prints different lists in 5 of the 56" in full
    assert "; Brihat Jataka 9.1–7" in compact


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
