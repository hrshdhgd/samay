from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from samay import qa, service
from samay.engine import house_effects as hx
from samay.engine.ephemeris import Chart, Placement
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render.text import render_answer

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
SIGN = {n: i for i, n in enumerate(["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio",
                                     "sagittarius", "capricorn", "aquarius", "pisces"])}


@pytest.fixture
def checked(tmp_path) -> Path:
    raw = yaml.safe_load(hx.RULES_PATH.read_text())
    raw["verification"] = {"level": "translation-checked", "checked_by": "test"}
    path = tmp_path / "ch20.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))
    hx.load_rules.cache_clear()
    yield path
    hx.load_rules.cache_clear()


def chart(lagna: str, **places) -> Chart:
    """A chart with planets at the middle of the given signs (others far from the Sun, in Gemini)."""
    planets = {g: Placement(SIGN["gemini"] * 30 + 15) for g in ("moon", "mars", "mercury", "jupiter", "venus", "saturn",
                                                                 "rahu", "ketu")}
    planets["sun"] = Placement(SIGN["sagittarius"] * 30 + 15)
    for g, sign in places.items():
        planets[g] = Placement(SIGN[sign] * 30 + 15, retrograde=g.endswith("_r"))
    return Chart(datetime(2000, 1, 1, tzinfo=UTC), 0, 0, 24.0, SIGN[lagna] * 30 + 1, planets)


def test_shipped_rules_are_checked_and_cover_the_seven_planets():
    hx.load_rules.cache_clear()
    rules = hx.load_rules()
    assert rules.servable and rules.checked_by == "h2" and len(rules.effects) > 60
    assert {e["planet"] for e in rules.effects} == set(hx.PLANETS)
    r = hx.reading(chart("aries", saturn="cancer"), "saturn")  # Saturn in the 4th: the Sun's effects there
    assert r is not None and r.level == "translation-checked" and r.effects[0].borrowed_from == "sun"


def test_a_rules_file_that_nobody_has_checked_is_never_used(tmp_path):
    import yaml

    raw = yaml.safe_load(hx.RULES_PATH.read_text())
    raw["verification"] = {"level": "unchecked"}
    path = tmp_path / "unchecked.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))
    hx.load_rules.cache_clear()
    try:
        assert not hx.load_rules(path).servable
        assert hx.reading(chart("aries", saturn="cancer"), "saturn", path) is None
    finally:
        hx.load_rules.cache_clear()


@pytest.mark.parametrize(
    "planet,sign,expected",
    [
        ("sun", "aries", "exaltation"), ("sun", "libra", "depression"), ("sun", "leo", "moolatrikona"),
        ("moon", "taurus", "exaltation"),  # also its moolatrikona: exaltation wins
        ("moon", "cancer", "own"), ("saturn", "capricorn", "own"), ("saturn", "aquarius", "moolatrikona"),
        ("saturn", "taurus", "friendly"),  # Venus rules Taurus; Venus is Saturn's friend (II.17)
        ("saturn", "sagittarius", "neutral"),  # Jupiter is Saturn's neutral
        ("saturn", "cancer", "inimical"),  # the Moon is Saturn's enemy
        ("jupiter", "gemini", "inimical"), ("mars", "gemini", "inimical"), ("mercury", "cancer", "inimical"),
    ],
)
def test_strength_follows_the_text(checked, planet, sign, expected):
    assert hx.strength(hx.load_rules(checked), planet, SIGN[sign]) == expected


def test_astangata_uses_the_limit_and_the_retrograde_limit(checked):
    rules = hx.load_rules(checked)
    sun = SIGN["sagittarius"] * 30 + 15
    c = chart("aries")
    near = Chart(c.utc, 0, 0, 24.0, c.ascendant, {**c.planets, "venus": Placement(sun + 9),
                                                  "mercury": Placement(sun - 13, retrograde=True)})
    assert hx.is_astangata(rules, "venus", near)  # 9 <= 10
    assert not hx.is_astangata(rules, "mercury", near)  # retrograde limit 12 < 13
    assert not hx.is_astangata(rules, "sun", near)


def test_lagna_specific_row_replaces_the_general_one(checked):
    general = hx.reading(chart("taurus", saturn="taurus"), "saturn", checked)  # Saturn in 1st, Taurus lagna
    special = hx.reading(chart("libra", saturn="libra"), "saturn", checked)  # Libra lagna: the exception
    assert general.house == special.house == 1
    assert general.effects[0].text.startswith("such person will be poor")
    assert [e.text for e in special.effects] == [
        "the person will be as happy as a king, will rule over a village or a town, will be learned and will possess fine limbs"]


def test_borrowed_effects_say_whose_they_are(checked):
    r = hx.reading(chart("aries", saturn="cancer"), "saturn", checked)  # Saturn in the 4th
    assert r.house == 4 and [(e.text, e.borrowed_from) for e in r.effects] == [
        ("the person will be afflicted with grief and mental sufferings", "sun")]


def test_venus_in_pisces_adds_its_own_line(checked):
    r = hx.reading(chart("aries", venus="pisces"), "venus", checked)  # 12th house, borrowed from Jupiter
    assert [e.text for e in r.effects] == ["he will do fearful deeds",
                                           "if Venus occupy sign Pisces at the time of birth the person will become rich"]


def test_rahu_and_ketu_are_not_in_chapter_20(checked):
    assert hx.reading(chart("aries"), "rahu", checked) is None


def test_shares_follow_stanza_11_and_its_note(checked):
    rules = hx.load_rules(checked)
    r = hx.reading(chart("aries", saturn="libra"), "saturn", checked)  # exaltation
    assert hx.shares(rules, r) == {"good": "fully", "bad": "not at all"}
    r = hx.reading(chart("aries", saturn="sagittarius", sun="leo"), "saturn", checked)  # neutral: stanza 11 is silent
    assert hx.shares(rules, r) == {"good": None, "bad": None}


def test_hidden_rows_are_left_out(checked):
    raw = yaml.safe_load(checked.read_text())
    for e in raw["effects"]:
        if e["planet"] == "sun" and e.get("house") == 4:
            e["hidden"] = True
    checked.write_text(yaml.safe_dump(raw, allow_unicode=True))
    hx.load_rules.cache_clear()
    assert hx.reading(chart("aries", saturn="cancer"), "saturn", checked).effects == ()


@pytest.mark.parametrize("bad", [{"planet": "pluto", "house": 1, "kind": "good", "verse": 1, "text": "x"},
                                 {"planet": "sun", "house": 1, "kind": "great", "verse": 1, "text": "x"},
                                 {"planet": "sun", "kind": "good", "verse": 1, "text": "x"},
                                 {"planet": "sun", "house": 1, "kind": "good", "verse": 1, "text": "x", "when_lagna": ["ophiuchus"]}])
def test_malformed_rows_are_rejected(checked, bad):
    raw = yaml.safe_load(checked.read_text())
    raw["effects"].append(bad)
    checked.write_text(yaml.safe_dump(raw))
    hx.load_rules.cache_clear()
    with pytest.raises(ValueError):
        hx.load_rules(checked)


@needs_kernel
def test_answer_shows_the_quote_the_strength_rule_and_the_frame(checked, monkeypatch):
    monkeypatch.setattr(hx, "RULES_PATH", checked)
    monkeypatch.setattr(hx.reading, "__defaults__", (checked,))
    birth = service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))  # Saturn, Sagittarius, 2nd house
    text = render_answer(qa.answer_topic("planet:saturn", birth, datetime(2026, 11, 9, tzinfo=UTC)))
    assert "What Brihat Jataka chapter 20 says about Saturn in your 2nd house:" in text
    assert "will have his wealth carried away by the king" in text and "same effects as Sun" in text
    assert "Your Saturn is in Sagittarius, a neutral planet's sign." in text
    assert "gives no share for a neutral sign" in text
    assert "It is not a forecast" in text


def test_obscured_planet_gets_the_astangata_shares(checked):
    rules = hx.load_rules(checked)
    r = hx.reading(chart("aries", saturn="sagittarius"), "saturn", checked)  # on top of the Sun
    assert r.astangata and hx.shares(rules, r) == {"good": "not at all", "bad": "fully"}


@pytest.mark.parametrize("share,phrase", [("fully", "the bad effects come to pass in full"),
                                           ("not at all", "the bad effects do not come to pass"),
                                           ("three-quarters", "three-quarters of the bad effects come to pass"),
                                           (None, "it gives no share of the bad effects here")])
def test_share_phrases(share, phrase):
    from samay.render.text import _share_phrase

    assert _share_phrase("bad", share) == phrase
