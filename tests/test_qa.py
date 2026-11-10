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
        ("what does the 4th house mean", "house:4"),
        ("tell me about house 10", "house:10"),
        ("what is the seventh house", "house:7"),
        ("what is my lagna", "house:1"),
        ("what does ascendant mean", "house:1"),
        ("what about the 13th house", None),
        ("Saturn in my 4th house?", "planet:saturn"),  # the planet leads; its house is added
        ("what is the cosmic person", "concept:kalapurusha"),
    ],
)
def test_rule_based_sorter(question, topic):
    assert qa.sort_question(question) == topic


def test_every_topic_is_a_valid_storable_key():
    from samay.engine.entries import is_topic

    assert all(is_topic(t) for t in qa.TOPICS) and len(qa.TOPICS) == 32


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


def test_checked_entries_are_returned_in_source_order_without_birth():
    a = qa.answer_topic("planet:moon", None, NOW)
    assert [e.id for e in a.entries] == [
        "bj-2-1-moon", "bj-2-2-names-moon", "bj-2-4-colour-moon", "bj-2-6-nature-moon", "bj-2-8-appearance-moon"]
    assert a.facts == () and a.notes == ()


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


def test_rahu_and_ketu_always_get_the_astronomy_note_alongside_their_entries():
    for node in ("rahu", "ketu"):
        a = qa.answer_topic(f"planet:{node}", None, NOW)
        assert [e.id for e in a.entries] == [f"bj-2-3-names-{node}"] and a.notes == (qa.RAHU_KETU_FACT,)
    assert qa.answer_topic("planet:saturn", None, NOW).notes == ()


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


def test_kalapurusha_question_gets_its_entry():
    assert [e.id for e in qa.answer_topic("concept:kalapurusha", None, NOW).entries] == ["bj-1-4-kalapurusha"]


def test_unchecked_entries_stay_hidden_from_answers(tmp_path):
    import yaml

    from samay.engine import entries as entry_store

    draft = {"id": "d", "topic": "planet:saturn", "system": "any", "english": "draft",
             "citation": {"text": "T", "chapter": 1, "verse": 1, "edition": "e"}, "verification": {"level": "unchecked"}}
    (tmp_path / "e.yaml").write_text(yaml.safe_dump([draft]))
    entry_store.load_entries.cache_clear()
    try:
        assert qa.answer_topic("planet:saturn", None, NOW, entries_dir=tmp_path).entries == ()
    finally:
        entry_store.load_entries.cache_clear()


def test_house_question_returns_the_checked_house_entries():
    a = qa.answer_topic("house:4", None, NOW)
    assert [e.id for e in a.entries] == ["bj-1-15-house-4", "bj-1-15-note-house-4"]
    assert "signifies relations" in a.entries[0].english and "Graha (dwelling place)" in a.entries[0].english
    assert "translator, N. Chidambaram Iyer" in a.entries[1].english  # the note says whose words it is
    assert all(e.verification.checked_by == "h2" for e in a.entries)


def test_every_house_has_both_entries():
    for n in range(1, 13):
        assert [e.id for e in qa.answer_topic(f"house:{n}", None, NOW).entries] == [
            f"bj-1-15-house-{n}", f"bj-1-15-note-house-{n}"]


@needs_kernel
def test_planet_answer_with_a_birth_adds_the_entries_for_its_house(tmp_path):
    import yaml

    from samay.engine import entries as entry_store

    def entry(eid, topic):
        return {"id": eid, "topic": topic, "system": "any", "english": eid,
                "citation": {"text": "T", "chapter": 1, "verse": 1, "edition": "e"},
                "verification": {"level": "translation-checked", "checked_by": "t", "checked_on": "2026-11-10",
                                 "against": "t"}}

    (tmp_path / "e.yaml").write_text(yaml.safe_dump([entry("sat", "planet:saturn"), entry("h2", "house:2"),
                                                     entry("h4", "house:4")]))
    entry_store.load_entries.cache_clear()
    try:
        a = qa.answer_topic("planet:saturn", _birth(), NOW, entries_dir=tmp_path)  # Saturn is in the 2nd house here
        assert [e.id for e in a.entries] == ["sat", "h2"]
        assert [e.id for e in qa.answer_topic("planet:saturn", None, NOW, entries_dir=tmp_path).entries] == ["sat"]
    finally:
        entry_store.load_entries.cache_clear()


def test_the_ai_is_told_the_guardrails():
    for phrase in ("not science", "Do not predict specific events", "medical, legal or financial advice",
                   "never contradict them", "no markdown", "at most 120 words"):
        assert phrase in qa.AI_SYSTEM, phrase


def test_the_ai_prompt_carries_verified_facts_and_a_bounded_question():
    a = qa.answer_topic("planet:moon", None, NOW)
    prompt = qa._ai_prompt("x" * 2000, a)
    assert prompt.startswith("Verified facts:\n- Varahamihira describes the Moon as the mind")
    assert prompt.count("x") == qa.MAX_QUESTION_CHARS
    assert qa._ai_prompt("what is a nakshatra?", qa.Answer(None, (), ())) == "Question: what is a nakshatra?"


async def test_a_long_ai_reply_is_cut_at_a_word_with_an_ellipsis(model_on, monkeypatch):
    async def long_reply(*args, **kwargs):
        return "word " * 1000

    monkeypatch.setattr(narrate, "complete", long_reply)
    out = await qa.ai_answer("q", qa.Answer(None, (), ()))
    assert len(out) <= qa.MAX_AI_CHARS + 1 and out.endswith("word…")


async def test_ai_answer_is_none_when_the_model_says_nothing(model_on):
    assert await qa.ai_answer("q", qa.Answer(None, (), ()), _client("")) is None


def test_render_ai_labels_the_answer_and_adds_the_caveat():
    from samay.render.text import render_ai

    out = render_ai("Some words.")
    assert out.startswith("🤖 AI says: “Some words.”") and out.endswith("may be wrong.")


def test_wording_changes_only_when_an_ai_answer_follows():
    from samay.render.text import render_answer

    assert render_answer(qa.answer_topic(None, None, NOW), ai_follows=True) == "I have no checked source for this."
    unsourced = render_answer(qa.answer_topic("dasha:venus", None, NOW), birth_known=False, ai_follows=True)
    assert "I have noted the topic" in unsourced and "won't guess" not in unsourced
    assert "won't guess" in render_answer(qa.answer_topic("dasha:venus", None, NOW), birth_known=False)
