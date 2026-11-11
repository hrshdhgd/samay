from datetime import UTC, datetime

import pytest

from samay import qa, service
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render.text import render_answer
from samay.subject import SELF, Subject, clean

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
NOW = datetime(2026, 11, 11, tzinfo=UTC)
MAYA = Subject("Maya", "daughter")


def test_wording_for_the_user_and_for_another_person():
    assert (SELF.your, SELF.Your, SELF.you_are, SELF.heading) == ("your", "Your", "you are", "")
    assert (MAYA.your, MAYA.Your, MAYA.you_are) == ("Maya's", "Maya's", "Maya is")
    assert MAYA.heading == "👤 Maya (daughter)" and Subject("Maya").heading == "👤 Maya"


def test_clean_keeps_text_safe_and_bounded():
    assert clean("  Maya\n\t Rao  ", 40) == "Maya Rao"
    assert clean("A" * 100, 10) == "A" * 10
    assert clean("Ma\x00ya\x1b[31m", 40) == "Maya[31m"  # control characters are dropped


@needs_kernel
def test_the_same_question_is_answered_about_another_person_in_their_name():
    birth = service.resolve_birth(BirthInput("2015-03-14", "06:30", "Pune"))
    own = render_answer(qa.answer_topic("future:overview", birth, NOW))
    hers = render_answer(qa.answer_topic("future:overview", birth, NOW, subject=MAYA))
    assert own.startswith("🔮 Your current period of life") and "From your chart" not in own
    assert hers.startswith("👤 Maya (daughter)\n\n🔮 Maya's current period of life")
    assert "Maya's" in hers and "Inside it Maya is in the" in hers and "from Maya's Moon sign" in hers
    assert "your" not in hers.replace("Your", "").lower().replace("yourself", "")  # nothing left addressed to the asker


@needs_kernel
def test_a_planet_and_a_life_area_answer_use_the_persons_name_too():
    birth = service.resolve_birth(BirthInput("2015-03-14", "06:30", "Pune"))
    planet = render_answer(qa.answer_topic("planet:saturn", birth, NOW, subject=MAYA), "full")
    assert "In Maya's birth chart, Saturn is in" in planet and "from Maya's lagna" in planet and "From Maya's chart:" in planet
    assert "in your" not in planet.lower()
    life = render_answer(qa.answer_topic("life:marriage", birth, NOW, subject=MAYA))
    assert "Maya's 7th house is in" in life and "what sits there in Maya's chart" in life
    dasha = render_answer(qa.answer_topic("dasha:jupiter", birth, NOW, subject=MAYA))
    assert "Maya's Jupiter chapter (dasha) lasts 16 years" in dasha
    assert any(status in dasha for status in ("Maya is in it now", "it is still ahead", "it has ended"))
    assert "you are in it now" not in dasha


def test_default_subject_leaves_the_answer_exactly_as_before():
    answer = qa.answer_topic("planet:venus", None, NOW)
    assert answer.who is SELF and render_answer(answer, birth_known=False).startswith("Varahamihira describes Venus")


def test_a_minor_subject_adds_the_note_to_the_answer_and_an_adult_does_not():
    child = qa.answer_topic("planet:venus", None, NOW, subject=Subject("Maya", "daughter", minor=True))
    text = render_answer(child, birth_known=True)
    assert text.splitlines()[:3] == ["👤 Maya (daughter)", "", "ⓘ The classical texts describe adult life, so for a child this is only a general reading."]
    assert "ⓘ The classical texts" not in render_answer(qa.answer_topic("planet:venus", None, NOW, subject=Subject("Raj")))
    assert "ⓘ The classical texts" not in render_answer(qa.answer_topic("planet:venus", None, NOW))
