from datetime import UTC, datetime

import httpx
import pytest

from samay import narrate, qa, service
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
NOW = datetime(2026, 11, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    "question,topic",
    [
        ("What does Saturn stand for?", "planet:saturn"),
        ("tell me about shani", "planet:saturn"),
        ("What is Guru?", "planet:jupiter"),
        ("what about my Rahu", "planet:rahu"),
        ("When does my Venus dasha end?", "dasha:venus"),
        ("what is my current mahadasha", "dasha:current"),
        ("Which period am I in?", "dasha:current"),
        ("Will I get married this year?", None),
        ("namaste", None),
        ("", None),
        ("Mars and Venus together?", "planet:mars"),  # the first planet named
        ("What is Kalapurusha?", "concept:kalapurusha"),
        ("what is the cosmic person", "concept:kalapurusha"),
    ],
)
def test_rule_based_sorter(question, topic):
    assert qa.sort_question(question) == topic


def test_every_topic_is_a_valid_storable_key():
    from samay.engine.entries import is_topic

    assert all(is_topic(t) for t in qa.TOPICS) and len(qa.TOPICS) == 20


def _client(reply):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"response": reply})))


@pytest.fixture
def model_on(monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_URL", "http://ollama.test")


async def test_model_sorter_accepts_only_known_keys(model_on):
    assert await qa.sort_with_model("what's the deal with the ringed one", _client("planet:saturn")) == "planet:saturn"
    assert await qa.sort_with_model("whatever", _client(" `dasha:venus`.\n")) == "dasha:venus"
    assert await qa.sort_with_model("will I be rich", _client("none")) is None


async def test_model_sorter_falls_back_to_rules_on_unknown_keys_or_failure(model_on):
    assert await qa.sort_with_model("what is shani", _client("planet:pluto")) == "planet:saturn"
    assert await qa.sort_with_model("what is shani", _client("Saturn is a planet of discipline")) == "planet:saturn"
    broken = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert await qa.sort_with_model("what is shani", broken) == "planet:saturn"


async def test_model_sorter_is_unused_when_the_model_is_off(monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_URL", "")
    assert await qa.sort_with_model("what is shani") == "planet:saturn"


def _birth():
    return service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))


def test_answer_without_a_topic_is_empty():
    assert qa.answer_topic(None, None, NOW) == qa.Answer(None, (), ())
    assert qa.answer_topic("planet:pluto", None, NOW).topic is None


def test_checked_entry_is_returned_word_for_word_without_birth():
    a = qa.answer_topic("planet:moon", None, NOW)
    assert [e.id for e in a.entries] == ["bj-2-1-moon"] and a.facts == () and a.notes == ()


@needs_kernel
def test_planet_facts_come_from_the_persons_chart():
    a = qa.answer_topic("planet:saturn", _birth(), NOW)
    assert a.facts == (("In your birth chart, Saturn is in Sagittarius (Dhanu), the 2nd house from your lagna "
                       "(rising sign), and was moving backwards (retrograde)."),)


@needs_kernel
def test_current_dasha_resolves_to_the_running_chapter_and_shows_its_dates():
    a = qa.answer_topic("dasha:current", _birth(), NOW)
    assert a.topic == "dasha:jupiter" and a.entries == ()
    assert a.facts == ("Your Jupiter chapter (dasha) lasts 16 years: Feb 2017 – Feb 2033; you are in it now.",)


@needs_kernel
def test_past_and_future_chapters_are_labelled():
    assert "it has ended" in qa.answer_topic("dasha:moon", _birth(), NOW).facts[0]
    assert "it is still ahead" in qa.answer_topic("dasha:saturn", _birth(), NOW).facts[0]


def test_current_dasha_without_birth_stays_general():
    a = qa.answer_topic("dasha:current", None, NOW)
    assert a.topic == "dasha:current" and a.facts == ()


def test_rahu_without_an_entry_gets_the_astronomy_note():
    a = qa.answer_topic("planet:rahu", None, NOW)
    assert a.entries == () and a.notes == (qa.RAHU_KETU_FACT,)


@pytest.mark.parametrize(
    "question,line",
    [
        ("What does Shani stand for?", "Shani is the Sanskrit and Hindi name for Saturn."),
        ("tell me about guru", "Guru is the Sanskrit and Hindi name for Jupiter."),
        ("what is shukra", "Shukra is the Sanskrit and Hindi name for Venus."),
        ("what is saturn", None),
        ("is shani the same as saturn?", None),  # the English name is already in the question
        ("what is rahu", None),
    ],
)
def test_answer_names_the_planet_when_asked_by_its_sanskrit_name(question, line):
    assert qa.answer_topic(qa.sort_question(question), None, NOW, question=question).name_line == line


def test_name_line_comes_first_in_the_rendered_answer():
    from samay.render.text import render_answer

    q = "What does Shani stand for?"
    text = render_answer(qa.answer_topic(qa.sort_question(q), None, NOW, question=q), birth_known=False)
    assert text.startswith("Shani is the Sanskrit and Hindi name for Saturn.\n\nVarahamihira describes Saturn")


def test_unchecked_entries_stay_hidden_from_answers():
    saturn = qa.answer_topic("planet:saturn", None, NOW)
    assert [e.id for e in saturn.entries] == ["bj-2-1-saturn"]
    assert qa.answer_topic("concept:kalapurusha", None, NOW).entries == ()
