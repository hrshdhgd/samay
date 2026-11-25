"""A personal reading for one day ("what does my day look like tomorrow"): the sorter, the day's facts from the engine,
the sourced answer when the model is off, and the forward-looking AI prompt when it is on."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from samay import narrate, panchang_qa, qa, service
from samay.engine import antardasha, ashtakavarga, geo, gochara
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render import prompts
from samay.render.text import DISCLAIMER, render_answer
from samay.subject import Subject

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 24, 7, 0, tzinfo=IST)


def _birth():
    return service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune"))


def _pune():
    return geo.find_places("Pune")[0]


def _real(mod):
    return getattr(mod.load_rules, "__wrapped_real__", mod.load_rules)


@pytest.fixture
def checked_rules(monkeypatch):
    """The rules files as shipped (checked), instead of the test suite's default unchecked view."""
    for mod in (gochara, antardasha, ashtakavarga):
        monkeypatch.setattr(mod, "load_rules", _real(mod))


# --- the sorter ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "topic"),
    [
        ("What does my day look like tomorrow", "future:tomorrow"),
        ("what does my day look like today?", "future:today"),
        ("How will my day be tomorrow", "future:tomorrow"),
        ("how will my day be", "future:today"),
        ("How will tomorrow be for me", "future:tomorrow"),
        ("what will today be like for me", "future:today"),
        ("is tomorrow a good day for me", "future:tomorrow"),
        ("how is my day going to be today", "future:today"),
        ("what is my horoscope for tomorrow", "future:tomorrow"),
        # not a day reading: a period, a planet, a life area, a panchang fact or nothing personal
        ("how will my week be", "future:week"),
        ("what will my week be like from tomorrow", "future:week"),
        ("what will Saturn do to me today", "planet:saturn"),
        ("is today good for my career", "life:career"),
        ("tell me my horoscope", "future:overview"),
        ("what is the tithi tomorrow", None),
        ("what is today's nakshatra", None),
        ("what day is it today", None),
        ("what will happen to me", None),
        ("what a lovely day", None),
        ("tell me about my week tomorrow onwards", "future:week"),
    ],
)
def test_the_offline_rules_find_a_day_reading(question, topic):
    assert qa.sort_question(question) == topic


@pytest.mark.parametrize(
    "question",
    [
        "What does my day look like tomorrow",
        "how will my day be",
        "How will tomorrow be for me",
        "what will today be like for me",
        "is tomorrow a good day for me",
    ],
)
def test_a_personal_day_question_is_not_taken_by_the_panchang_answers(question):
    assert panchang_qa.sort(question) is None


@pytest.mark.parametrize(
    "question",
    ["what is the tithi tomorrow", "nakshatra tomorrow", "is it Ekadashi today", "panchang for today"],
)
def test_panchang_questions_stay_panchang_questions(question):
    assert panchang_qa.sort(question) is not None


def test_the_router_knows_the_day_topics():
    for topic in qa.DAY_TOPICS:
        assert topic in qa.TOPICS and f"- {topic}:" in qa.MODEL_SYSTEM
        assert qa._parse_route(f"{topic} | me", set()) == qa.Route(topic, "me")
    assert not set(qa.DAY_TOPICS) & set(
        qa.OUTLOOK_TOPICS
    )  # "day" is a span for the engine, not its own topic
    assert "future:day" not in qa.TOPICS


def test_day_readings_are_forward_looking_and_not_sensitive():
    for topic in qa.DAY_TOPICS:
        a = qa.Answer(topic, (), ())
        assert qa.is_prediction(a) and qa.is_forecast(a) and qa.sensitivity(topic, qa.SELF) is None
    assert qa.is_forecast(qa.Answer("future:week", (), ()))
    assert not qa.is_forecast(qa.Answer("when:marriage", (), ()))
    assert not qa.is_forecast(qa.Answer("future:overview", (), ()))


# --- the day's facts ----------------------------------------------------------------------------------------------


@needs_kernel
def test_tomorrow_is_the_next_local_day_at_home_with_its_panchang_and_rahu_kaala():
    report = service.day_report(_birth(), NOW, "tomorrow", _pune())
    assert report.which == "tomorrow" and report.day == date(2026, 11, 25)
    midnight = datetime(2026, 11, 25, tzinfo=IST)
    assert report.outlook.span == "day" and report.outlook.tz == "Asia/Kolkata"
    assert report.outlook.start == midnight.astimezone(UTC)
    assert report.outlook.end == (midnight + timedelta(days=1)).astimezone(UTC)
    assert report.place_label is not None and "Pune" in report.place_label
    assert report.panchang is not None and report.panchang.facts.day == date(2026, 11, 25)
    assert report.rahu is not None and report.rahu.start.astimezone(IST).date() == date(2026, 11, 25)
    assert {s.planet for s in report.outlook.stays} == set(gochara.GRAHAS)
    assert report.outlook.dasha_at_start is not None


@needs_kernel
def test_today_uses_the_home_calendar_day_not_the_utc_one():
    late = datetime(2026, 11, 24, 20, 0, tzinfo=UTC)  # already 25 November in Pune
    assert service.day_report(_birth(), late, "today", _pune()).day == date(2026, 11, 25)


@needs_kernel
def test_without_a_home_the_utc_day_is_used_and_there_is_no_panchang():
    late = datetime(2026, 11, 24, 20, 0, tzinfo=UTC)
    report = service.day_report(_birth(), late, "today", None)
    assert report.day == date(2026, 11, 24) and report.outlook.tz == "UTC"
    assert report.panchang is None and report.rahu is None and report.place_label is None


@needs_kernel
def test_the_day_facts_hold_the_moon_sign_panchang_rahu_kaala_and_running_chapter(checked_rules):
    report = service.day_report(_birth(), NOW, "tomorrow", _pune())
    facts = "\n".join(qa.day_facts(report))
    f = report.panchang.facts
    maha, antar = report.outlook.dasha_at_start
    assert "Wednesday 25 Nov 2026" in facts
    assert f"Moon sign, {qa.SIGNS[report.outlook.moon_sign]}" in facts
    assert f.tithi.name in facts and f.nakshatra.name in facts
    assert f"{report.rahu.start.astimezone(IST):%H:%M}" in facts and "Rahu Kaala" in facts
    assert maha.lord.title() in facts and antar.lord.title() in facts
    moon = next(s for s in report.outlook.stays if s.planet == "moon")
    assert moon.effect and moon.effect in facts  # the checked transit result for the Moon


@needs_kernel
def test_unchecked_transit_results_are_never_given_as_facts():
    report = service.day_report(_birth(), NOW, "tomorrow", _pune())
    assert all(s.effect is None for s in report.outlook.stays) and report.outlook.antardasha == ()
    facts = "\n".join(qa.day_facts(report))
    assert "the text gives" not in facts and "Phaladeepika 21" not in facts
    assert "Rahu Kaala" in facts  # the positions and the day's panchang are still facts


def test_without_a_birth_the_day_answer_asks_for_one():
    answer = qa.answer_topic("future:tomorrow", None, NOW)
    assert answer.day is None and render_answer(answer, birth_known=False) == prompts.NEED_BIRTH_FOR_FUTURE


# --- the sourced answer (model off) -----------------------------------------------------------------------------


@needs_kernel
def test_the_sourced_day_answer_in_plain_words(checked_rules):
    answer = qa.answer_topic("future:tomorrow", _birth(), NOW, home=_pune())
    text = render_answer(answer)
    f = answer.day.panchang.facts
    assert text.startswith("🔮 Your day tomorrow: Wednesday 25 Nov 2026")
    assert f.tithi.name in text and f.nakshatra.name in text and "Rahu Kaala" in text
    assert "What the old book says the day brings:" in text and "Source: Phaladeepika 26.2–8" in text
    assert prompts.OUTLOOK_FRAME in text and text.endswith(DISCLAIMER)
    assert "Rahu Kaala" in text and "UTC" not in text


@needs_kernel
def test_the_sourced_day_answer_with_unchecked_rules_shows_no_meanings():
    text = render_answer(qa.answer_topic("future:today", _birth(), NOW, home=_pune()))
    assert text.startswith("🔮 Your day today: Tuesday 24 Nov 2026")
    assert prompts.OUTLOOK_PLAIN_UNCHECKED in text and "Source:" not in text


@needs_kernel
def test_without_a_home_the_sourced_answer_asks_where_they_live():
    text = render_answer(qa.answer_topic("future:today", _birth(), NOW))
    assert prompts.NEED_HOME_FOR_DAY in text and "UTC" not in text


@needs_kernel
def test_a_child_s_day_is_named_for_the_child():
    child = Subject("Maya", "daughter", True)
    text = render_answer(qa.answer_topic("future:tomorrow", _birth(), NOW, subject=child, home=_pune()))
    assert text.startswith("👤 Maya (daughter)") and "🔮 Maya's day tomorrow" in text


# --- the AI reading (model on) ----------------------------------------------------------------------------------


@pytest.fixture
def captured(monkeypatch):
    calls = []

    async def fake(system, prompt, client=None, **_kw):
        calls.append({"system": system, "prompt": prompt})
        return "Tomorrow tends to favour steady work."

    monkeypatch.setattr(narrate, "complete", fake)
    return calls


def test_the_forecast_prompt_allows_an_informed_reading_inside_the_old_limits():
    s = qa.AI_FORECAST_SYSTEM
    for phrase in (
        "forward-looking",
        "four to six short sentences",
        "tends to",
        "a good day for",
        "better to hold off on",
        "only the supplied facts",
        "Never invent planet positions, dates, times, events",
        "medical, legal or financial advice",
        "Never speak of death, serious illness or accidents",
        "not a guarantee",
        "keep a child's reading gentle",
        "no markdown",
    ):
        assert phrase in s, phrase
    assert "do not present anything as likely, expected, or a prediction" not in s


@needs_kernel
async def test_the_day_reading_prompt_carries_the_day_s_facts_and_the_new_wording(captured, checked_rules):
    answer = qa.answer_topic("future:tomorrow", _birth(), NOW, home=_pune())
    question = "What does my day look like tomorrow"
    reply = await qa.ai_answer(question, answer, source_answer=render_answer(answer, ai_follows=True))
    assert reply == "Tomorrow tends to favour steady work."
    (call,) = captured
    assert call["system"] == qa.AI_FORECAST_SYSTEM
    f = answer.day.panchang.facts
    for fact in (f.tithi.name, f.nakshatra.name, "Rahu Kaala", "Wednesday 25 Nov 2026", question):
        assert fact in call["prompt"], fact
    assert "Selected answer topic: future:tomorrow." in call["prompt"]


@needs_kernel
async def test_a_week_reading_uses_the_forecast_prompt_and_a_when_question_keeps_the_old_one(captured):
    birth = _birth()
    await qa.ai_answer("how is my week", qa.answer_topic("future:week", birth, NOW))
    await qa.ai_answer("when will I marry", qa.answer_topic("when:marriage", birth, NOW))
    assert [c["system"] for c in captured] == [qa.AI_FORECAST_SYSTEM, qa.AI_PREDICT_SYSTEM]


@needs_kernel
async def test_a_child_s_day_reading_stays_gentle(captured):
    child = Subject("Maya", "daughter", True)
    answer = qa.answer_topic("future:tomorrow", _birth(), NOW, subject=child, home=_pune())
    await qa.ai_answer("how will Maya's day be tomorrow", answer)
    assert "They are a child. Keep the reading gentle" in captured[0]["prompt"]


def test_with_the_model_off_no_ai_reading_is_asked_for(monkeypatch):
    monkeypatch.setattr(narrate, "OLLAMA_URL", "")
    assert not narrate.enabled()


def test_the_forecast_caveat_labels_the_ai_reading():
    from samay.render.text import render_ai

    text = render_ai("Tomorrow tends to favour steady work.", True, forecast=True)
    assert text.endswith(prompts.AI_FORECAST_CAVEAT)
    assert (
        prompts.AI_FORECAST_CAVEAT.startswith("🤖 AI reading")
        and "not a guarantee" in prompts.AI_FORECAST_CAVEAT
    )


def test_the_day_topics_are_computed_so_no_miss_is_recorded():
    assert all(t.startswith(qa.COMPUTED_PREFIXES) for t in qa.DAY_TOPICS)


def test_the_day_span_is_short_steps_over_one_day():
    length, step, planets, vedha = service.OUTLOOK_SPANS["day"]
    assert length == timedelta(days=1) and step <= timedelta(hours=3) and "moon" in planets and vedha
