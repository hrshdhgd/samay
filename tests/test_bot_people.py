"""Asking about other people through the Telegram handlers: narrative intake, saving, switching, /people."""
import itertools
import json
import logging
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from samay import narrate, narrative, qa
from samay.bot import app as bot
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render import prompts
from samay.store import MAX_PEOPLE, Store

ME, OTHER_CHAT = 111, 222
needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
STORY = ("My daughter Maya was born on 14 March 2015 at 6:30 in the morning in Pune, India, and my son Arjun on "
         "2 November 2018 at 9 in the evening in Mumbai. What will their future be like?")
EXTRACTED = {"people": [
    {"name": "Maya", "relation": "daughter", "date": "2015-03-14", "time": "06:30", "time_certain": True, "place": "Pune, India"},
    {"name": "Arjun", "relation": "son", "date": "2018-11-02", "time": "21:00", "time_certain": True, "place": "Mumbai"}],
    "question": "What will their future be like?", "about": ""}

_ids = itertools.count(1)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


@pytest.fixture
def ctx(store):
    app = SimpleNamespace(bot_data={bot.STORE_KEY: store, bot.ALLOWED_KEY: frozenset({ME, OTHER_CHAT})})
    return SimpleNamespace(application=app, error=None, args=[])


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(bot, "_monotonic", lambda: now["t"])
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 11, 15, 0, tzinfo=UTC))
    return now


def message(chat, text):
    msg = SimpleNamespace(text=text, reply_text=AsyncMock(), reply_photo=AsyncMock())
    return SimpleNamespace(update_id=next(_ids), effective_chat=SimpleNamespace(id=chat), effective_message=msg,
                           callback_query=None), msg


def tap(chat, data):
    msg = SimpleNamespace(text=None, reply_text=AsyncMock(), reply_photo=AsyncMock())
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_media=AsyncMock(), edit_message_text=AsyncMock())
    return SimpleNamespace(update_id=next(_ids), effective_chat=SimpleNamespace(id=chat), effective_message=msg,
                           callback_query=query), msg


def texts(msg):
    return [c.args[0] for c in msg.reply_text.await_args_list]


def buttons(call):
    markup = call.kwargs.get("reply_markup")
    return {b.text: b.callback_data for row in getattr(markup, "inline_keyboard", []) for b in row}


def last_buttons(msg):
    return buttons(msg.reply_text.await_args)


@pytest.fixture
def ai(monkeypatch):
    """The model is on and scripted: `route` answers the router (a string, or a function of its prompt), `extract` the
    reader of narratives, `ai` the open answer."""
    monkeypatch.setattr(narrate, "OLLAMA_URL", "http://ollama.test")
    cfg = {"route": "none", "extract": json.dumps(EXTRACTED), "ai": "A thoughtful reading.", "calls": []}

    async def fake(system, prompt, client=None, model=None, timeout=None, max_tokens=None):
        cfg["calls"].append({"system": system, "prompt": prompt})
        if system == qa.MODEL_SYSTEM:
            return cfg["route"](prompt) if callable(cfg["route"]) else cfg["route"]
        if system == narrative.EXTRACT_SYSTEM:
            return cfg["extract"]
        return cfg["ai"]

    monkeypatch.setattr(narrate, "complete", fake)
    return cfg


def story_router(prompt):
    return "people:add" if "Message: My daughter" in prompt else "future:overview"


async def do_intake(ctx, ai, answer_choices=("Yes, just for now", "💾 Yes, save Arjun")):
    """The whole conversation: the story, then the confirmation of each child. Returns every message text sent."""
    ai["route"] = story_router
    update, msg = message(ME, STORY)
    await bot.on_text(update, ctx)
    sent = texts(msg)
    for choice in answer_choices:
        data = next(d for label, d in last_buttons(msg).items() if label.startswith(choice.split()[0]) and choice in label)
        update, msg = tap(ME, data)
        await bot.on_button(update, ctx)
        sent += texts(msg)
    return sent


# ------------------------------------------------------------------------------------------------------
@needs_kernel
async def test_a_story_about_two_children_is_read_checked_saved_and_the_question_answered_for_both(ctx, store, ai, clock):
    sent = await do_intake(ctx, ai)
    assert sent[0].startswith("Here is what I understood:") and "👤 Maya (daughter)" in sent[0]
    assert "Born 14 Mar 2015, 6:30 am" in sent[0] and "After this I'll check the details for Arjun." in sent[0]
    assert "👤 Arjun (son)\nBorn 02 Nov 2018, 9:00 pm" in sent[1]
    assert sent[2] == prompts.PERSON_DONE.format(name="Arjun") + "\n" + prompts.PEOPLE_SAVED_LIST.format(names="Arjun")
    answers = [t for t in sent[3:] if t.startswith("👤")]
    assert [a.splitlines()[0] for a in answers] == ["👤 Maya (daughter)", "👤 Arjun (son)"]  # the question, for each
    assert all("current period of life" in a for a in answers) and "Maya's current period of life" in answers[0]
    assert sum(t.startswith("🤖 AI says:") for t in sent) == 2  # and the model's own words after each
    assert [(p.name, p.relation) for p in store.list_people(ME)] == [("Arjun", "son")]  # Maya was "just for now"


@needs_kernel
async def test_the_model_is_told_whom_the_question_is_about(ctx, ai, clock):
    await do_intake(ctx, ai)
    prompts_to_ai = [c["prompt"] for c in ai["calls"] if c["system"] == qa.AI_SYSTEM]
    assert any("The question is about Maya, the writer's daughter." in p for p in prompts_to_ai)
    assert any("The question is about Arjun, the writer's son." in p for p in prompts_to_ai)


async def test_the_router_is_given_the_people_and_who_we_are_talking_about(ctx, store, ai, clock):
    store.save_person(ME, "Maya", "daughter", BirthInput("2015-03-14", "06:30", "Pune"))
    ai["route"] = "none"
    update, _ = message(ME, "hello")
    await bot.on_text(update, ctx)
    prompt = next(c["prompt"] for c in ai["calls"] if c["system"] == qa.MODEL_SYSTEM)
    assert "People: me (the person writing); Maya (daughter)" in prompt and "Currently talking about: me" in prompt


@needs_kernel
async def test_follow_ups_move_between_the_people_and_back_to_the_user(ctx, store, ai, clock):
    await do_intake(ctx, ai)
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    headings = []
    for i, reply in enumerate(("life:marriage | Arjun", "life:career | Maya", "life:career | me", "life:children")):
        ai["route"] = reply
        update, msg = message(ME, f"follow-up number {i}")  # distinct texts: an identical repeat is ignored
        await bot.on_text(update, ctx)
        headings.append(texts(msg))
    assert headings[0][0].startswith("👤 Arjun (son)") and "On marriage and partnership" in headings[0][0]
    assert headings[1][0].startswith("👤 Maya (daughter)") and "On work and career" in headings[1][0]
    assert headings[2][0] == prompts.SWITCHED_SELF and not headings[2][1].startswith("👤")  # back to the user's own
    assert not headings[3][0].startswith("👤")  # and it stays there


@needs_kernel
async def test_the_model_cannot_invent_a_person(ctx, store, ai, clock):
    await do_intake(ctx, ai)
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    ai["route"] = "life:marriage | Rohit"  # not in the list: ignored, so the active person (Arjun) stays
    update, msg = message(ME, "what about Rohit's marriage")
    await bot.on_text(update, ctx)
    assert texts(msg)[0].startswith("👤 Arjun (son)")


@needs_kernel
async def test_without_the_model_a_saved_persons_first_name_is_enough(ctx, store, clock):
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    store.save_person(ME, "Maya", "daughter", BirthInput("2015-03-14", "06:30", "Pune"))
    update, msg = message(ME, "tell me about maya's career")
    await bot.on_text(update, ctx)
    assert texts(msg)[0].startswith("👤 Maya (daughter)") and "On work and career" in texts(msg)[0]
    update, msg = message(ME, "what does saturn mean")  # no name: stays with Maya
    await bot.on_text(update, ctx)
    assert texts(msg)[0].startswith("👤 Maya (daughter)") and "In Maya's birth chart" in texts(msg)[0]


@needs_kernel
async def test_buttons_under_an_answer_stay_tied_to_the_person_it_was_about(ctx, store, ai, clock):
    await do_intake(ctx, ai)
    ai["route"] = "planet:venus | Maya"
    update, msg = message(ME, "what is venus for maya")
    await bot.on_text(update, ctx)
    first = msg.reply_text.await_args_list[0]
    more = buttons(first)[prompts.BTN_MORE]
    assert more.startswith("qa:full@") and more.endswith(":planet:venus")
    ai["route"] = "life:career | Arjun"  # the conversation moves on to Arjun
    update, _ = message(ME, "and Arjun's career")
    await bot.on_text(update, ctx)
    update, _ = tap(ME, more)  # a tap on Maya's old message
    await bot.on_button(update, ctx)
    shown = update.callback_query.edit_message_text.await_args.args[0]
    assert shown.startswith("👤 Maya (daughter)") and "Arjun" not in shown and shown.count("• ") >= 3


async def test_a_tap_for_a_person_who_has_been_deleted_is_answered_kindly(ctx, store):
    pid = store.save_person(ME, "Maya", None, BirthInput("2015-03-14", "06:30", "Pune"))
    store.delete_person(ME, pid)
    update, msg = tap(ME, f"qa:full@{pid}:planet:venus")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.PERSON_GONE] and update.callback_query.edit_message_text.await_count == 0


async def test_a_person_whose_chart_cannot_be_worked_out_is_explained_not_guessed(ctx, store, clock):
    store.save_person(ME, "Maya", None, BirthInput("2015-03-14", "06:30", "Springfield, US"))  # many places, none chosen
    update, msg = message(ME, "maya saturn")
    await bot.on_text(update, ctx)
    assert texts(msg) == [prompts.PERSON_UNRESOLVED.format(name="Maya")]


# ------------------------------------------------------------------------------------------------------
async def test_people_lists_saved_and_not_saved_people_and_lets_you_choose(ctx, store, ai, clock):
    saved = store.save_person(ME, "Maya", "daughter", BirthInput("2015-03-14", "06:30", "Pune"))
    await do_intake(ctx, ai, answer_choices=("Yes, just for now", "Yes, just for now"))
    update, msg = message(ME, "/people")
    await bot.cmd_people(update, ctx)
    labels = last_buttons(msg)
    assert any(label.startswith("Maya (daughter)") for label in labels)
    assert any("Arjun (son) · not saved" in label for label in labels) and prompts.BTN_ADD_PERSON in labels
    update, msg = tap(ME, f"ppl:use:{saved}")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.SWITCHED.format(name="Maya")]
    update, msg = tap(ME, "ppl:me")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.SWITCHED_SELF]


async def test_delete_asks_first_then_removes_one_person_only(ctx, store):
    a = store.save_person(ME, "Maya", None, BirthInput("2015-03-14", "06:30", "Pune"))
    b = store.save_person(ME, "Arjun", None, BirthInput("2018-11-02", "21:00", "Mumbai"))
    update, msg = tap(ME, f"ppl:del:{a}")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.ASK_DELETE_PERSON.format(name="Maya")] and store.get_person(ME, a) is not None
    update, msg = tap(ME, f"ppl:delno:{a}")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.KEPT] and store.get_person(ME, a) is not None
    update, msg = tap(ME, f"ppl:delyes:{a}")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.PERSON_DELETED.format(name="Maya")]
    assert store.get_person(ME, a) is None and store.get_person(ME, b) is not None


async def test_deleting_the_person_we_are_talking_about_returns_to_the_user(ctx, store):
    a = store.save_person(ME, "Maya", None, BirthInput("2015-03-14", "06:30", "Pune"))
    update, _ = tap(ME, f"ppl:use:{a}")
    await bot.on_button(update, ctx)
    update, _ = tap(ME, f"ppl:delyes:{a}")
    await bot.on_button(update, ctx)
    assert bot._session(ctx, ME)["active"] is None


async def test_one_chat_cannot_choose_or_delete_another_chats_person(ctx, store):
    mine = store.save_person(ME, "Maya", None, BirthInput("2015-03-14", "06:30", "Pune"))
    for action in ("use", "del", "delyes"):
        update, msg = tap(OTHER_CHAT, f"ppl:{action}:{mine}")
        await bot.on_button(update, ctx)
        assert texts(msg) == [prompts.PERSON_GONE]
    assert store.get_person(ME, mine) is not None and bot._session(ctx, OTHER_CHAT)["active"] is None


async def test_bad_people_buttons_do_nothing(ctx):
    for data in ("ppl:", "ppl:use:abc", "ppl:use:", "ppl:nonsense:1", "ppl:use:99999"):
        update, msg = tap(ME, data)
        await bot.on_button(update, ctx)
        assert len(texts(msg)) <= 1 and "Traceback" not in "".join(texts(msg))


async def test_add_someone_starts_a_narrative_when_the_model_is_on_and_steps_when_it_is_not(ctx, store, ai, clock):
    update, msg = tap(ME, "ppl:add")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.ASK_NARRATE] and store.get_draft(ME)["step"] == "narrate"


async def test_add_someone_without_the_model_asks_for_a_name(ctx, store, clock):
    update, msg = tap(ME, "ppl:add")
    await bot.on_button(update, ctx)
    assert texts(msg) == [prompts.ASK_NAME]


@needs_kernel
async def test_a_story_sent_after_add_someone_is_read_without_asking_the_router(ctx, store, ai, clock):
    update, _ = tap(ME, "ppl:add")
    await bot.on_button(update, ctx)
    ai["extract"] = json.dumps({"people": [EXTRACTED["people"][0]], "question": "", "about": ""})
    update, msg = message(ME, "Maya, my daughter, born 14 March 2015 at 6:30 am in Pune, India")
    await bot.on_text(update, ctx)
    assert "👤 Maya (daughter)" in texts(msg)[0]
    assert not any(c["system"] == qa.MODEL_SYSTEM for c in ai["calls"])


async def test_when_the_story_cannot_be_read_we_carry_on_step_by_step(ctx, store, ai, clock):
    ai["route"] = story_router
    ai["extract"] = "sorry, I cannot do that"
    update, msg = message(ME, STORY)
    await bot.on_text(update, ctx)
    assert texts(msg) == [prompts.NARRATE_FAILED + "\n\n" + prompts.ASK_NAME]
    assert store.get_draft(ME)["step"] == "name" and store.get_draft(ME)["purpose"] == "person"


async def test_fix_something_at_the_confirmation_asks_again(ctx, store, ai, clock):
    ai["route"] = story_router
    update, msg = message(ME, STORY)
    await bot.on_text(update, ctx)
    update, msg = tap(ME, last_buttons(msg)[prompts.BTN_FIX])
    await bot.on_button(update, ctx)
    assert texts(msg)[0].startswith("When was Maya born?")


# ------------------------------------------------------------------------------------------------------
async def test_the_limit_is_explained_and_the_person_is_kept_for_now(ctx, store, ai, clock):
    for i in range(MAX_PEOPLE):
        store.save_person(ME, f"Person{i}", None, BirthInput("2015-03-14", "06:30", "Pune"))
    ai["route"] = story_router
    ai["extract"] = json.dumps({"people": [EXTRACTED["people"][0]], "question": "", "about": ""})
    update, msg = message(ME, STORY)
    await bot.on_text(update, ctx)
    update, msg = tap(ME, last_buttons(msg)["💾 Yes, save Maya"])
    await bot.on_button(update, ctx)
    assert prompts.PEOPLE_FULL.format(limit=MAX_PEOPLE) in texts(msg)[0]
    assert len(store.list_people(ME)) == MAX_PEOPLE and bot._session(ctx, ME)["guests"]  # kept in memory for now


@needs_kernel
async def test_forget_me_deletes_saved_people_and_what_was_remembered(ctx, store, ai, clock):
    await do_intake(ctx, ai)
    assert store.list_people(ME) and bot._session(ctx, ME)["guests"]
    update, _ = tap(ME, bot.FORGET_YES)
    await bot.on_button(update, ctx)
    assert store.list_people(ME) == [] and bot._recent_turns(ctx, ME) == []
    assert bot._session(ctx, ME)["guests"] == {} and bot._session(ctx, ME)["active"] is None


@needs_kernel
async def test_nothing_about_the_people_or_the_conversation_reaches_the_disk_or_the_log(ctx, store, ai, clock, caplog):
    with caplog.at_level(logging.DEBUG):
        await do_intake(ctx, ai)
    with sqlite3.connect(store.path) as c:
        dump = "\n".join(c.iterdump())
    for word in ("Maya", "Arjun", "daughter", "2018", "Mumbai", "future be like", "Pune"):
        assert word not in dump, word
    for word in ("Maya", "Arjun", "2018", "future be like"):
        assert word not in caplog.text, word


@needs_kernel
async def test_the_conversation_about_people_expires_with_the_conversation(ctx, store, ai, clock):
    await do_intake(ctx, ai)
    clock["t"] += bot.CHAT_TTL_SECONDS + 1
    assert bot._session(ctx, ME)["active"] is None and bot._session(ctx, ME)["guests"] == {}


async def test_a_stranger_cannot_add_or_see_people(store, ai):
    app = SimpleNamespace(bot_data={bot.STORE_KEY: store, bot.ALLOWED_KEY: frozenset({ME})})
    stranger_ctx = SimpleNamespace(application=app, error=None, args=[])
    for handler, update in ((bot.cmd_people, message(999, "/people")[0]), (bot.on_text, message(999, STORY)[0]),
                            (bot.on_button, tap(999, "ppl:add")[0])):
        await handler(update, stranger_ctx)
    assert not any(c["system"] == narrative.EXTRACT_SYSTEM for c in ai["calls"]) and store.list_people(999) == []


async def test_people_is_a_registered_command_and_menu_button(store):
    app = bot.build_application("123:abc", frozenset({ME}), store)
    commands = {c for h in app.handlers[0] if hasattr(h, "commands") for c in h.commands}
    assert "people" in commands and "people" in prompts.COMMANDS
    assert prompts.MENU_PEOPLE in [b for row in prompts.MENU_ROWS for b in row]
    assert "/people" in prompts.help_text()


# --- children: the texts describe adult life ----------------------------------------------------------------


@needs_kernel
async def test_answers_about_a_child_carry_the_adult_life_note_and_the_ai_is_told_to_be_gentle(ctx, store, ai, clock):
    store.save_person(ME, "Maya", "daughter", BirthInput("2015-03-14", "06:30", "Pune"))   # 11 years old
    store.save_person(ME, "Raj", "brother", BirthInput("1985-06-15", "08:30", "Pune"))     # an adult
    ai["route"] = "life:marriage | Maya"
    update, msg = message(ME, "maya marriage")
    await bot.on_text(update, ctx)
    assert texts(msg)[0].splitlines()[:3] == ["👤 Maya (daughter)", "", prompts.MINOR_NOTE]
    child_prompt = next(c["prompt"] for c in ai["calls"] if c["system"] == qa.AI_SYSTEM)
    assert "They are a child. Keep the reading gentle" in child_prompt
    ai["route"] = "life:marriage | Raj"
    update, msg = message(ME, "raj marriage")
    await bot.on_text(update, ctx)
    assert prompts.MINOR_NOTE not in texts(msg)[0]
    adult_prompt = [c["prompt"] for c in ai["calls"] if c["system"] == qa.AI_SYSTEM][-1]
    assert "They are a child" not in adult_prompt


async def test_the_age_line_is_exactly_eighteen_years(ctx, store, ai, clock):
    # "now" is 2026-11-11: born 2008-11-12 is still 17, born 2008-11-10 is 18.
    store.save_person(ME, "Younger", None, BirthInput("2008-11-12", "08:00", "Pune"))
    store.save_person(ME, "Older", None, BirthInput("2008-11-10", "08:00", "Pune"))
    young = await bot._subject_and_birth(ctx, ME, store.list_people(ME)[0].id)
    old = await bot._subject_and_birth(ctx, ME, store.list_people(ME)[1].id)
    assert young[0].minor is True and old[0].minor is False


# --- the consent gate for sensitive answers --------------------------------------------------------------------------------
from samay.engine import longevity


def _tap_with_markup(chat, data):
    update, msg = tap(chat, data)
    update.callback_query.edit_message_reply_markup = AsyncMock()
    return update, msg


def _computed(monkeypatch):
    """Records every call to qa.answer_topic, so a test can prove nothing was computed before consent."""
    calls = []
    real = qa.answer_topic

    def spy(topic, *a, **k):
        calls.append(topic)
        return real(topic, *a, **k)

    monkeypatch.setattr(qa, "answer_topic", spy)
    return calls


def test_only_the_longevity_topic_is_sensitive_and_health_is_sensitive_for_children():
    from samay.subject import SELF, Subject
    child = Subject("Maya", "daughter", minor=True)
    assert qa.sensitivity("chart:longevity", SELF) == "sensitive" and qa.sensitivity("chart:longevity", child) == "child"
    assert qa.sensitivity("chart:health", SELF) is None and qa.sensitivity("chart:health", child) == "child"
    assert qa.sensitivity("planet:saturn", child) is None and qa.sensitivity(None, child) is None
    assert qa.sensitivity("future:week", child) is None


@needs_kernel
async def test_a_question_about_length_of_life_gets_a_warning_first_and_nothing_is_computed(ctx, store, clock, monkeypatch):
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    calls = _computed(monkeypatch)
    update, msg = message(ME, "how long will I live, when will I die")
    await bot.on_text(update, ctx)
    sent = [c.args[0] for c in msg.reply_text.await_args_list]
    assert sent == [prompts.SENS_WARN] and calls == []
    buttons = [b for row in msg.reply_text.await_args_list[0].kwargs["reply_markup"].inline_keyboard for b in row]
    assert [b.text for b in buttons] == [prompts.BTN_SENS_YES, prompts.BTN_SENS_NO]
    assert buttons[0].callback_data == "sens:yes:chart:longevity" and buttons[1].callback_data == "sens:no"


@needs_kernel
async def test_the_warning_is_the_same_even_when_the_model_is_on_and_the_ai_is_never_asked(ctx, store, clock, ai):
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    ai["route"] = "chart:longevity"
    update, msg = message(ME, "will I live long?")
    await bot.on_text(update, ctx)
    assert [c.args[0] for c in msg.reply_text.await_args_list] == [prompts.SENS_WARN]
    assert all(call["system"] != qa.AI_SYSTEM for call in ai["calls"])


@needs_kernel
async def test_declining_shows_nothing_and_accepting_shows_the_answer_once_without_the_ai(ctx, store, clock, ai, monkeypatch):
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    rules = longevity.load_rules()
    import dataclasses
    monkeypatch.setattr(longevity, "load_rules", lambda path=None: dataclasses.replace(rules, level="translation-checked", checked_by="t"))
    update, msg = _tap_with_markup(ME, "sens:no")
    await bot.on_button(update, ctx)
    assert [c.args[0] for c in msg.reply_text.await_args_list] == [prompts.SENS_DECLINED]
    ai["calls"].clear()
    update, msg = _tap_with_markup(ME, "sens:yes:chart:longevity")
    await bot.on_button(update, ctx)
    sent = [c.args[0] for c in msg.reply_text.await_args_list]
    assert len(sent) == 1 and "length of life" in sent[0] and "not a forecast" in sent[0]
    update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)  # the buttons are removed after the tap
    assert ai["calls"] == []


@needs_kernel
async def test_a_child_gets_the_stronger_warning_with_their_name_for_length_of_life_and_for_health(ctx, store, clock, ai, monkeypatch):
    pid = store.save_person(ME, "Maya", "daughter", BirthInput("2015-03-14", "06:30", "Pune"))
    state = bot._session(ctx, ME)
    state["active"] = pid
    calls = _computed(monkeypatch)
    for question, topic in (("how long will she live", "chart:longevity"), ("what diseases might she have", "chart:health")):
        ai["route"] = topic
        update, msg = message(ME, question)
        await bot.on_text(update, ctx)
        sent = [c.args[0] for c in msg.reply_text.await_args_list]
        assert sent == [prompts.SENS_WARN_CHILD.format(name="Maya")], question
        yes = msg.reply_text.await_args_list[0].kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        assert yes.startswith(f"sens:yes@{pid}:chart:")
    assert calls == []


@needs_kernel
async def test_an_adult_is_not_warned_about_health_and_a_child_is_warned_even_if_the_button_is_replayed(ctx, store, clock):
    store.save_user(ME, BirthInput("1952-08-15", "06:30", "Pune"))
    update, msg = message(ME, "what diseases might I have")
    await bot.on_text(update, ctx)
    assert prompts.SENS_WARN not in [c.args[0] for c in msg.reply_text.await_args_list]
    # a crafted More/Less button for a sensitive topic does nothing (it must come through the warning)
    pid = store.save_person(ME, "Maya", "daughter", BirthInput("2015-03-14", "06:30", "Pune"))
    update, msg = tap(ME, f"qa:full@{pid}:chart:health")
    update.callback_query.edit_message_text = AsyncMock()
    await bot.on_button(update, ctx)
    update.callback_query.edit_message_text.assert_not_awaited()
    update, msg = tap(ME, "qa:full:chart:longevity")
    update.callback_query.edit_message_text = AsyncMock()
    await bot.on_button(update, ctx)
    update.callback_query.edit_message_text.assert_not_awaited()


@needs_kernel
async def test_a_consent_tap_for_a_deleted_person_or_a_wrong_topic_is_ignored(ctx, store, clock):
    update, msg = _tap_with_markup(ME, "sens:yes@999:chart:longevity")
    await bot.on_button(update, ctx)
    assert [c.args[0] for c in msg.reply_text.await_args_list] == [prompts.PERSON_GONE]
    for data in ("sens:yes:planet:saturn", "sens:yes:nonsense", "sens:yes@x:chart:longevity", "sens:yes"):
        update, msg = _tap_with_markup(ME, data)
        await bot.on_button(update, ctx)
        msg.reply_text.assert_not_awaited()


@needs_kernel
async def test_the_consent_is_not_remembered_between_questions(ctx, store, clock):
    store.save_user(ME, BirthInput("1990-08-15", "14:30", "Pune"))
    for _ in range(2):
        update, msg = message(ME, f"how long will I live {next(_ids)}")
        await bot.on_text(update, ctx)
        assert [c.args[0] for c in msg.reply_text.await_args_list] == [prompts.SENS_WARN]
        yes = _tap_with_markup(ME, "sens:yes:chart:longevity")
        await bot.on_button(*[yes[0], ctx])
