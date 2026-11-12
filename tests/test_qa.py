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
        ("Will I get married this year?", "life:marriage"),  # a single keyword; the model reads the whole message
        ("what is the wedding season", "life:marriage"),
        ("how is my career", "life:career"),
        ("will I go abroad", "life:travel"),
        ("buying property", "life:home"),
        ("my studies", "life:education"),
        ("what does my current dasha mean for my son's marriage", "dasha:current"),  # a dasha word wins
        ("what does saturn mean for marriage", "planet:saturn"),  # a planet named wins
        ("namaste", None),
        ("", None),
        ("Mars and Venus together?", "planet:mars"),  # the first planet named
        ("What is Kalapurusha?", "concept:kalapurusha"),
        ("what is a dasha", "concept:dasha"),
        ("explain the dasha system", "concept:dasha"),
        ("what dasha is it now", "dasha:current"),
        ("how long does my dasha last", "dasha:current"),
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

    assert all(is_topic(t) for t in qa.TOPICS) and len(qa.TOPICS) == 71


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
def test_current_dasha_resolves_to_the_running_chapter_and_shows_its_dates(empty_entries):
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
    for phrase in ("not science", "medical, legal or financial advice",
                   "never contradict them", "no markdown", "at most 150 words",
                   "Never state that a specific event will or will not happen", "talk naturally"):
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


def test_wording_changes_only_when_an_ai_answer_follows(empty_entries):
    from samay.render.text import render_answer

    assert render_answer(qa.answer_topic(None, None, NOW), ai_follows=True) == "I have no checked source for this."
    unsourced = render_answer(qa.answer_topic("dasha:venus", None, NOW), birth_known=False, ai_follows=True)
    assert "I have noted the topic" in unsourced and "won't guess" not in unsourced
    assert "won't guess" in render_answer(qa.answer_topic("dasha:venus", None, NOW), birth_known=False)


def test_shipped_dasha_entries_cover_every_planet_from_the_vimshottari_verses_only():
    from samay.engine.entries import load_entries

    load_entries.cache_clear()
    ph = {e.id: e for e in load_entries() if e.id.startswith("ph-19-")}
    assert {e.topic for e in ph.values()} == {"concept:dasha", *(f"dasha:{g}" for g in qa.GRAHAS)}
    assert all(e.system == "vimshottari" for e in ph.values())
    assert sorted(int(e.citation["verse"]) for e in ph.values()) == [2, *range(18, 27)]  # not verses 5-17
    order = ["sun", "moon", "mars", "rahu", "jupiter", "saturn", "mercury", "ketu", "venus"]  # the text's order, v. 18-26
    assert [ph[f"ph-19-{18 + i}-{g}"].topic for i, g in enumerate(order)] == [f"dasha:{g}" for g in order]
    assert all("Phaladeepika" in e.english or "Mantreswara" in e.english for e in ph.values())


def _checked_dasha_entry(system="vimshottari"):
    return {"id": "d", "topic": "dasha:saturn", "system": system, "english": "listed effects",
            "citation": {"text": "Phaladeepika", "chapter": 19, "verse": "23", "edition": "e"},
            "verification": {"level": "translation-checked", "checked_by": "t", "checked_on": "2026-11-10",
                             "against": "t"}}


def test_a_dasha_answer_with_sourced_entries_carries_the_not_a_forecast_frame(tmp_path):
    import yaml

    from samay.engine import entries as entry_store
    from samay.render import prompts
    from samay.render.text import render_answer

    (tmp_path / "e.yaml").write_text(yaml.safe_dump([_checked_dasha_entry()]))
    entry_store.load_entries.cache_clear()
    try:
        text = render_answer(qa.answer_topic("dasha:saturn", None, NOW, entries_dir=tmp_path), birth_known=False)
        assert "listed effects" in text and prompts.DASHA_FRAME in text and "not a forecast" in text
        assert text.index("listed effects") < text.index(prompts.DASHA_FRAME)
        other = render_answer(qa.answer_topic("planet:saturn", None, NOW, entries_dir=tmp_path), birth_known=False)
        assert prompts.DASHA_FRAME not in other  # the frame belongs to dasha answers only
    finally:
        entry_store.load_entries.cache_clear()


def test_an_entry_for_a_different_dasha_system_never_answers_a_vimshottari_question(tmp_path):
    import yaml

    from samay.engine import entries as entry_store

    (tmp_path / "e.yaml").write_text(yaml.safe_dump([_checked_dasha_entry(system="brihat-jataka-dasa")]))
    entry_store.load_entries.cache_clear()
    try:
        assert qa.answer_topic("dasha:saturn", None, NOW, entries_dir=tmp_path).entries == ()
    finally:
        entry_store.load_entries.cache_clear()


# --- the model reads the message; the rules are only a fallback -------------------------------------------


@pytest.mark.parametrize("text", ["What is my future", "tell me my horoscope"])
def test_offline_fallback_knows_a_few_single_words_for_the_future(text):
    assert qa.sort_question(text) == "future:overview"


def test_the_fallback_does_not_pattern_match_whole_questions():
    # Single words only ("marriage", "year"); a whole question is the model's job.
    for text in ("am I going to be lucky", "what will happen to me", "will I win the lottery"):
        assert qa.sort_question(text) is None


async def test_the_model_routes_any_wording_to_a_known_topic(model_on):
    for wording in ("will I ever get that promotion?", "anything good coming for me?", "my luck lately?"):
        assert await qa.sort_with_model(wording, _client("future:overview")) == "future:overview"


async def test_the_router_prompt_lists_the_topics_and_the_previous_one(model_on):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"response": "none"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await qa.sort_with_model("hello there", client, previous="planet:saturn") is None
    body = seen["body"]
    assert "Previous topic: planet:saturn" in body and "future:overview" in body and "small talk" in body
    assert "follow-up" in body and "dasha:<planet>" in body


async def test_the_ai_prompt_includes_recent_conversation_after_the_verified_facts(model_on, monkeypatch):
    captured = {}

    async def fake(system, prompt, client=None, model=None, timeout=None):
        captured["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(narrate, "complete", fake)
    answer = qa.answer_topic("planet:moon", None, NOW)
    await qa.ai_answer("and the sun?", answer, history=[("what is the moon?", "The Moon is the mind.")])
    prompt = captured["prompt"]
    assert prompt.index("Verified facts:") < prompt.index("Recent conversation:") < prompt.index("Question: and the sun?")
    assert "Person: what is the moon?\nYou: The Moon is the mind." in prompt


@needs_kernel
def test_the_future_reading_is_built_from_the_running_dasha_the_chart_and_the_transits():
    from samay.render.text import render_answer

    a = qa.answer_topic("future:overview", _birth(), NOW)
    assert a.topic == "future:overview" and [e.id for e in a.entries] == ["ph-19-22-jupiter"]  # Jupiter's chapter runs
    assert a.reading is not None and a.reading.planet == "jupiter"
    facts = " ".join(a.facts)
    assert "Venus sub-chapter until 02 Sep 2027" in facts and "Saturn is in Pisces (Meena), the 11th sign" in facts
    text = render_answer(a)
    assert text.startswith("🔮 Your current period of life")
    assert "Sources: Phaladeepika 19.22; Brihat Jataka 20." in text and "not a forecast" in text
    assert qa.answer_topic("future:overview", None, NOW).entries == ()
    assert render_answer(qa.answer_topic("future:overview", None, NOW), birth_known=False).startswith("To look at your future")


def test_the_answer_shows_one_lead_entry_and_one_source_line_unless_more_is_asked_for():
    from samay.render.text import render_answer

    answer = qa.answer_topic("planet:venus", None, NOW)
    compact, full = render_answer(answer, birth_known=False), render_answer(answer, "full", birth_known=False)
    assert compact.count("Varahamihira") == 1 and compact.count("Source:") == 1 and "(translation-checked)" not in compact
    assert full.count("• Varahamihira") >= 4 and "tr. N. Chidambaram Iyer" in full and "· checked" in full
    sanskrit = render_answer(answer, "sanskrit", birth_known=False)
    assert "मदनो" in sanskrit and sanskrit.count("ⓘ Verse text") == 1 and "Varahamihira" not in sanskrit


# --- life areas: marriage, career and the rest, read through the houses the text assigns -------------------


def test_every_life_area_points_at_houses_that_have_checked_entries():
    for area, (houses, label) in qa.LIFE_AREAS.items():
        answer = qa.answer_topic(f"life:{area}", None, NOW)
        assert {e.topic for e in answer.entries} == {f"house:{h}" for h in houses}, area
        assert label and answer.facts == ()


def test_marriage_is_the_seventh_house_and_says_what_the_text_gives_it():
    from samay.render.text import render_answer

    text = render_answer(qa.answer_topic("life:marriage", None, NOW), birth_known=False)
    assert text.startswith("On marriage and partnership: Brihat Jataka reads this from the 7th house of the chart.")
    assert "signifies wife" in text and "Manmatha (desire)" in text
    assert "cannot say whether or when anything will happen" in text


@needs_kernel
def test_marriage_with_a_birth_shows_the_house_its_sign_its_planets_and_their_readings():
    from samay.render.text import render_answer

    a = qa.answer_topic("life:marriage", _birth(), NOW)  # Pune 1990: Scorpio lagna, so the 7th house is Taurus (the Moon)
    assert a.facts == ("Your 7th house is in Taurus (Vrishabha), with Moon in it.",)
    assert [r.planet for r, _ in a.more_readings] == ["moon"]
    text = render_answer(a)
    assert "Moon in your 7th house" in text and "Sources:" in text


def test_the_model_can_route_a_marriage_question_to_its_area(model_on):
    import asyncio

    assert asyncio.run(qa.sort_with_model("will my marriage work out?", _client("life:marriage"))) == "life:marriage"


async def test_the_router_prompt_describes_the_life_areas_and_warns_against_forcing_a_topic(model_on):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"response": "none"})

    await qa.sort_with_model("what about marriage?", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert "life:<area>" in seen["body"] and "marriage" in seen["body"] and "a wrong topic is worse than" in seen["body"]


def test_the_ai_sees_the_planets_readings_for_a_life_area():
    a = qa.Answer("life:marriage", (), (), more_readings=())
    assert "Question: q" in qa._ai_prompt("q", a)


def _models_client(replies):
    """A client answering per model name; records which models were asked, in order."""
    asked = []

    def handler(request):
        import json
        model = json.loads(request.read())["model"]
        asked.append(model)
        return httpx.Response(200, json={"response": replies.get(model, "")})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), asked


async def test_an_unusable_small_model_route_is_retried_once_on_the_larger_model(model_on, monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_MODEL", "small")
    monkeypatch.setattr(narrate, "AI_MODEL", "large")
    client, asked = _models_client({"small": "Saturn is a planet of discipline", "large": "planet:saturn"})
    assert (await qa.route_with_model("the ringed one?", client)).topic == "planet:saturn"
    assert asked == ["small", "large"]


async def test_a_usable_small_model_route_never_calls_the_larger_model(model_on, monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_MODEL", "small")
    monkeypatch.setattr(narrate, "AI_MODEL", "large")
    client, asked = _models_client({"small": "none", "large": "planet:saturn"})
    assert (await qa.route_with_model("hello", client)).topic is None
    assert asked == ["small"]


async def test_no_retry_when_both_models_are_the_same_and_rules_decide_if_both_fail(model_on, monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_MODEL", "same")
    monkeypatch.setattr(narrate, "AI_MODEL", "same")
    client, asked = _models_client({"same": "gibberish"})
    assert (await qa.route_with_model("what is shani", client)).topic == "planet:saturn"
    assert asked == ["same"]
    monkeypatch.setattr(narrate, "AI_MODEL", "large")
    client, asked = _models_client({})  # a silent small model (timeout, down) is not retried on the slower one
    assert (await qa.route_with_model("what is shani", client)).topic == "planet:saturn"
    assert asked == ["same"]


@pytest.mark.parametrize("text", [
    "I have a person born 14th Aug 1989 at noon in Mumbai India - when will they get married?",
    "my son was born on 02/11/2018 at 9pm in Mumbai",
    "Maya, birth date 2015-03-14, Pune",
    "born August 14, 1989 in Mumbai",
])
def test_a_message_giving_a_birth_date_is_a_request_to_add_a_person(text):
    assert qa.describes_birth(text)
    assert qa.rule_route(text) == qa.Route(None, None, True)


@pytest.mark.parametrize("text", [
    "when will I get married?", "what happens in August 1989?", "I was born in Pune", "the 7th house in 2026",
])
def test_a_date_or_a_birth_word_alone_is_not_enough(text):
    assert not qa.describes_birth(text)


async def test_a_silent_model_still_recognises_a_message_that_describes_someone(model_on):
    route = await qa.route_with_model("born 14th Aug 1989 at noon in Mumbai, when will they marry?", _client(""))
    assert route.add
