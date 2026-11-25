import asyncio

"""Bot adapter: allowlist, wiring, persistence and logging. Handlers are driven with stub updates."""
import itertools
import logging
import os
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from samay.bot import app as bot
from samay.engine import geo
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render import prompts
from samay.store import Store

ALLOWED, STRANGER = 111, 999
needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "bot.db")


@pytest.fixture
def ctx(store):
    application = SimpleNamespace(bot_data={bot.STORE_KEY: store, bot.ALLOWED_KEY: frozenset({ALLOWED})})
    return SimpleNamespace(application=application, error=None, args=[])


_update_ids = itertools.count(1)


def message(chat_id: int, text: str):
    msg = SimpleNamespace(text=text, reply_text=AsyncMock(), reply_photo=AsyncMock())
    return (
        SimpleNamespace(
            update_id=next(_update_ids),
            effective_chat=SimpleNamespace(id=chat_id),
            effective_message=msg,
            callback_query=None,
        ),
        msg,
    )


def tap(chat_id: int, data: str):
    msg = SimpleNamespace(text=None, reply_text=AsyncMock(), reply_photo=AsyncMock())
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_media=AsyncMock())
    return (
        SimpleNamespace(
            effective_chat=SimpleNamespace(id=chat_id),
            effective_message=msg,
            callback_query=query,
        ),
        msg,
    )


def last_reply(msg) -> str:
    return msg.reply_text.await_args.args[0]


def last_buttons(msg) -> list:
    markup = msg.reply_text.await_args.kwargs["reply_markup"]
    return [b for row in markup.inline_keyboard for b in row]


# --- start-up and access ------------------------------------------------------------------------


def test_empty_or_bad_allowlist_refuses_to_start():
    for text in ("", " , ", "abc", "1,x"):
        with pytest.raises(SystemExit):
            bot.parse_allowed(text)
    assert bot.parse_allowed("12, 34") == frozenset({12, 34})


@pytest.fixture
def no_token_or_env_file(monkeypatch, tmp_path):
    """Neither a real token nor the developer's own .env may leak into these tests."""
    monkeypatch.setenv("SAMAY_ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("SAMAY_TELEGRAM_BOT_TOKEN", raising=False)


def test_missing_token_refuses_to_start(monkeypatch, no_token_or_env_file):
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    with pytest.raises(SystemExit, match="TELEGRAM_TOKEN"):
        bot.main()


def test_env_file_supplies_settings_but_never_overrides_the_environment(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nALLOWED_CHAT_IDS=5, 6\nSAMAY_TEST_KEY='quoted'\nSAMAY_TEST_SET=from-file\n\nbad line\n"
    )
    monkeypatch.delenv("ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("SAMAY_TEST_KEY", raising=False)
    monkeypatch.setenv("SAMAY_TEST_SET", "from-env")
    bot.load_env_file(env)
    assert bot.parse_allowed(os.environ["ALLOWED_CHAT_IDS"]) == frozenset({5, 6})
    assert os.environ["SAMAY_TEST_KEY"] == "quoted" and os.environ["SAMAY_TEST_SET"] == "from-env"
    for name in ("ALLOWED_CHAT_IDS", "SAMAY_TEST_KEY"):
        monkeypatch.delenv(name, raising=False)
    bot.load_env_file(tmp_path / "missing.env")  # a missing file is fine


def test_alternative_token_variable_is_accepted(monkeypatch, no_token_or_env_file):
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("SAMAY_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(
        bot,
        "build_application",
        lambda *a: (_ for _ in ()).throw(RuntimeError("reached")),
    )
    with pytest.raises(RuntimeError, match="reached"):
        bot.main()


def test_application_registers_every_command(store):
    app = bot.build_application("123:abc", frozenset({1}), store)
    commands = {c for group in app.handlers.values() for h in group for c in getattr(h, "commands", ())}
    assert commands == set(prompts.COMMANDS)


async def test_strangers_get_no_reply_and_store_nothing(ctx, store):
    for handler in (bot.cmd_start, bot.cmd_birth, bot.cmd_forget, bot.on_text):
        update, msg = message(STRANGER, "hello")
        await handler(update, ctx)
        msg.reply_text.assert_not_awaited()
    update, msg = tap(STRANGER, "forget:yes")
    await bot.on_button(update, ctx)
    msg.reply_text.assert_not_awaited()
    assert store.get_draft(STRANGER) is None


# --- the guided conversation, end to end through the handlers -------------------------------------


@needs_kernel
async def test_full_conversation_saves_birth_and_shows_the_chart(ctx, store):
    update, msg = message(ALLOWED, "/birth")
    await bot.cmd_birth(update, ctx)
    assert last_reply(msg) == prompts.ASK_DATE
    for text in ("15 August 1952", "6:30"):
        update, msg = message(ALLOWED, text)
        await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.ASK_AMPM
    am = next(b for b in last_buttons(msg) if b.text == prompts.BTN_AM)
    update, msg = tap(ALLOWED, am.callback_data)
    await bot.on_button(update, ctx)
    update, msg = message(ALLOWED, "Pune, India")
    await bot.on_text(update, ctx)

    saved = store.get_user(ALLOWED)
    assert (saved.date_text, saved.time_text) == ("1952-08-15", "06:30")
    assert store.get_draft(ALLOWED) is None
    texts = [c.args[0] for c in msg.reply_text.await_args_list]
    assert texts[0] == prompts.SAVED and texts[1].startswith("Your rising sign")
    assert "Bombay Time" in texts[1]  # the caution that matters for a 1952 Indian birth
    assert "samay dev" not in texts[1] and "confidence:" not in texts[1] and "Profile:" not in texts[1]


async def test_draft_survives_a_restart(ctx, store):
    update, _ = message(ALLOWED, "/birth")
    await bot.cmd_birth(update, ctx)
    update, _ = message(ALLOWED, "15-08-1952")
    await bot.on_text(update, ctx)

    restarted = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                bot.STORE_KEY: Store(store.path),
                bot.ALLOWED_KEY: frozenset({ALLOWED}),
            }
        )
    )
    update, msg = message(ALLOWED, "18:30")
    await bot.on_text(update, restarted)
    assert last_reply(msg) == prompts.ASK_PLACE


async def test_stale_button_after_restart_offers_a_fresh_start(ctx):
    update, msg = tap(ALLOWED, "dead|am")
    await bot.on_button(update, ctx)
    assert last_reply(msg) == prompts.STALE
    assert last_buttons(msg)[0].callback_data == "new"


async def test_text_without_a_conversation_is_treated_as_a_question(ctx):
    update, msg = message(ALLOWED, "namaste")
    await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.NO_TOPIC


async def test_asking_for_a_chart_without_details_starts_the_conversation(ctx, store):
    update, msg = message(ALLOWED, prompts.MENU_CHART)
    await bot.on_text(update, ctx)
    assert last_reply(msg).startswith(prompts.NEED_BIRTH) and store.get_draft(ALLOWED) is not None


async def test_forget_asks_first_then_deletes_everything(ctx, store):
    store.save_user(ALLOWED, BirthInput("1952-08-15", "06:30", "Pune"))
    store.save_draft(ALLOWED, {"step": "date"})
    update, msg = message(ALLOWED, prompts.MENU_FORGET)
    await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.FORGET_ASK and store.get_user(ALLOWED) is not None

    update, msg = tap(ALLOWED, bot.FORGET_NO)
    await bot.on_button(update, ctx)
    assert last_reply(msg) == prompts.KEPT and store.get_user(ALLOWED) is not None

    update, msg = tap(ALLOWED, bot.FORGET_YES)
    await bot.on_button(update, ctx)
    assert last_reply(msg) == prompts.FORGOTTEN
    assert store.get_user(ALLOWED) is None and store.get_draft(ALLOWED) is None


# --- errors and logs -----------------------------------------------------------------------------


async def test_error_handler_logs_type_not_details_and_apologises(ctx, caplog):
    update, msg = message(ALLOWED, "x")
    ctx.error = ValueError("born 1952-08-15 06:30 in Pune")
    with caplog.at_level(logging.ERROR, logger="samay"):
        await bot.on_error(update, ctx)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "ValueError" in logged and str(ALLOWED) in logged
    assert "1952" not in logged and "Pune" not in logged
    assert last_reply(msg) == prompts.GENERIC_ERROR


def test_main_silences_loggers_that_print_the_bot_token(monkeypatch, no_token_or_env_file):
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    with pytest.raises(SystemExit):
        bot.main()
    for name in ("httpx", "httpcore", "telegram"):
        assert logging.getLogger(name).level == logging.WARNING


# --- "/" menu and /help ----------------------------------------------------------------------------


def _live_commands(store):
    app = bot.build_application("123:abc", frozenset({1}), store)
    return app, {c for h in app.handlers[0] if hasattr(h, "commands") for c in h.commands}


def test_every_registered_command_has_a_description_and_vice_versa(store):
    _, live = _live_commands(store)
    assert live == set(prompts.COMMANDS)
    assert all(0 < len(d) <= 256 for d in prompts.COMMANDS.values())  # Telegram's limit


async def test_menu_is_registered_from_live_handlers_in_the_defined_order(store):
    app, _ = _live_commands(store)
    fake = SimpleNamespace(handlers=app.handlers, bot=SimpleNamespace(set_my_commands=AsyncMock()))
    await bot._register_commands(fake)
    menu = fake.bot.set_my_commands.await_args.args[0]
    assert [c.command for c in menu] == list(prompts.COMMANDS)
    assert menu[0].command == "ask" and menu[0].description == prompts.COMMANDS["ask"]


async def test_a_command_without_a_description_stops_start_up(store):
    app, _ = _live_commands(store)
    handler = next(h for h in app.handlers[0] if hasattr(h, "commands"))
    handler.commands = frozenset({*handler.commands, "mystery"})
    fake = SimpleNamespace(handlers=app.handlers, bot=SimpleNamespace(set_my_commands=AsyncMock()))
    with pytest.raises(RuntimeError, match="mystery"):
        await bot._register_commands(fake)


async def test_help_lists_the_commands_and_the_first_step(ctx):
    update, msg = message(ALLOWED, "/help")
    await bot.cmd_help(update, ctx)
    text = last_reply(msg)
    for cmd in prompts.HELP_ORDER:
        assert f"/{cmd} – {prompts.COMMANDS[cmd]}" in text
    assert prompts.MENU_CHANGE in text and "/start" in text
    assert text != prompts.WELCOME


async def test_help_is_silent_for_strangers(ctx):
    update, msg = message(STRANGER, "/help")
    await bot.cmd_help(update, ctx)
    msg.reply_text.assert_not_awaited()


def test_a_rejected_token_exits_cleanly_without_printing_it(monkeypatch, no_token_or_env_file, capsys):
    from unittest.mock import MagicMock

    from telegram.error import InvalidToken

    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:SECRETTOKEN")
    fake = MagicMock()
    fake.run_polling.side_effect = InvalidToken("The token `123:SECRETTOKEN` was rejected by the server.")
    monkeypatch.setattr(bot, "build_application", lambda *a: fake)
    with pytest.raises(SystemExit) as exit_info:
        bot.main()
    assert "rejected the bot token" in str(exit_info.value) and "SECRETTOKEN" not in str(exit_info.value)
    assert exit_info.value.__cause__ is None and "SECRETTOKEN" not in capsys.readouterr().err


def test_start_up_keeps_retrying_when_telegram_is_unreachable(monkeypatch, no_token_or_env_file):
    from unittest.mock import MagicMock

    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("SAMAY_TELEGRAM_BOT_TOKEN", "123:abc")
    fake = MagicMock()
    monkeypatch.setattr(bot, "build_application", lambda *a: fake)
    bot.main()
    assert fake.run_polling.call_args.kwargs["bootstrap_retries"] == -1


# --- chart picture and its switches ----------------------------------------------------------------


def buttons_of(markup):
    return {b.text: b.callback_data for row in markup.inline_keyboard for b in row}


def test_chart_markup_offers_the_other_style_and_the_opposite_degrees_setting():
    assert buttons_of(bot.chart_markup("south", False)) == {
        "🔄 North Indian": "img:north:0",
        "🔢 Show degrees": "img:south:1",
    }
    assert buttons_of(bot.chart_markup("north", True)) == {
        "🔄 South Indian": "img:south:1",
        "🔢 Hide degrees": "img:north:0",
    }


def _save_pune(store):
    store.save_user(ALLOWED, BirthInput("1990-08-15", "14:30", "Pune"))


@needs_kernel
async def test_my_chart_sends_the_south_picture_first_then_the_text(ctx, store):
    _save_pune(store)
    update, msg = message(ALLOWED, prompts.MENU_CHART)
    await bot.on_text(update, ctx)
    photo = msg.reply_photo.await_args
    assert photo.kwargs["photo"][:8] == b"\x89PNG\r\n\x1a\n"
    assert buttons_of(photo.kwargs["reply_markup"]) == buttons_of(bot.chart_markup("south", False))
    assert last_reply(msg).startswith("Your rising sign")  # the text comes as its own message


@needs_kernel
async def test_buttons_redraw_the_picture_in_place(ctx, store):
    from telegram import InputMediaPhoto

    _save_pune(store)
    update, msg = tap(ALLOWED, "img:north:1")
    await bot.on_button(update, ctx)
    edit = update.callback_query.edit_message_media.await_args
    assert isinstance(edit.kwargs["media"], InputMediaPhoto)
    assert buttons_of(edit.kwargs["reply_markup"]) == buttons_of(bot.chart_markup("north", True))
    msg.reply_text.assert_not_awaited()  # edited in place, no new message


@needs_kernel
async def test_the_four_pictures_differ(ctx, store):
    _save_pune(store)
    pictures = set()
    for choice in ("south:0", "south:1", "north:0", "north:1"):
        update, _ = tap(ALLOWED, f"img:{choice}")
        await bot.on_button(update, ctx)
        pictures.add(
            update.callback_query.edit_message_media.await_args.kwargs["media"].media.input_file_content
        )
    assert len(pictures) == 4


@needs_kernel
async def test_double_tap_on_a_switch_is_ignored_but_other_errors_are_not(ctx, store):
    from telegram.error import BadRequest

    _save_pune(store)
    update, _ = tap(ALLOWED, "img:north:0")
    update.callback_query.edit_message_media.side_effect = BadRequest("Message is not modified")
    await bot.on_button(update, ctx)  # swallowed
    update.callback_query.edit_message_media.side_effect = BadRequest("Message to edit not found")
    with pytest.raises(BadRequest):
        await bot.on_button(update, ctx)


async def test_bad_switch_data_is_ignored_and_missing_details_start_the_conversation(ctx, store):
    for data in ("img:round:0", "img:south:2", "img:south", "img:"):
        update, msg = tap(ALLOWED, data)
        await bot.on_button(update, ctx)
        update.callback_query.edit_message_media.assert_not_awaited()
        msg.reply_text.assert_not_awaited()
    update, msg = tap(ALLOWED, "img:north:0")  # valid, but nothing saved yet
    await bot.on_button(update, ctx)
    assert last_reply(msg) == prompts.NEED_BIRTH


async def test_strangers_cannot_use_the_chart_switches(ctx, store):
    _save_pune(store)
    update, _ = tap(STRANGER, "img:north:0")
    await bot.on_button(update, ctx)
    update.callback_query.edit_message_media.assert_not_awaited()


# --- where I live, Rahu Kaala, and the morning message ---------------------------------------------


MAPLEWOOD = lambda: geo.find_places("Maplewood, MN")[0]


@needs_kernel
async def test_home_conversation_saves_the_city_and_shows_todays_rahu_kaala(ctx, store, monkeypatch):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, 15, 0, tzinfo=UTC))
    update, msg = message(ALLOWED, "/home")
    await bot.cmd_home(update, ctx)
    assert last_reply(msg) == prompts.ASK_HOME
    update, msg = message(ALLOWED, "Maplewood, Minnesota")
    await bot.on_text(update, ctx)
    texts = [c.args[0] for c in msg.reply_text.await_args_list]
    assert (
        "Maplewood" in texts[0] and texts[1].startswith("⚠ Rahu Kaala today: 8:") and "(Maplewood" in texts[1]
    )
    assert store.get_home(ALLOWED).place_id == MAPLEWOOD().id and store.get_draft(ALLOWED) is None


@needs_kernel
async def test_today_shows_rahu_kaala_for_the_home_city_or_asks_for_one(ctx, store, monkeypatch):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, 15, 0, tzinfo=UTC))
    _save_pune(store)
    update, msg = message(ALLOWED, prompts.MENU_TODAY)
    await bot.on_text(update, ctx)
    assert prompts.NEED_HOME in last_reply(msg) and prompts.MENU_HOME in last_reply(msg)
    store.save_home(ALLOWED, "Maplewood", MAPLEWOOD().id)
    update, msg = message(ALLOWED, "/today")
    await bot._command("today")(update, ctx)
    assert "Rahu Kaala today: 8:" in last_reply(msg) and "Transiting Saturn" not in last_reply(msg)


async def test_brief_without_a_home_city_asks_for_it_first(ctx, store):
    update, msg = message(ALLOWED, "/brief")
    await bot.cmd_brief(update, ctx)
    assert (
        last_reply(msg).startswith(prompts.BRIEF_NEED_HOME) and store.get_draft(ALLOWED)["purpose"] == "home"
    )


async def test_brief_buttons_turn_the_message_on_off_and_ignore_bad_choices(ctx, store):
    store.save_home(ALLOWED, "Maplewood", MAPLEWOOD().id)
    update, msg = message(ALLOWED, prompts.MENU_BRIEF)
    await bot.on_text(update, ctx)
    assert prompts.BRIEF_STATUS_OFF in last_reply(msg)
    assert list(buttons_of(msg.reply_text.await_args.kwargs["reply_markup"]).values()) == [
        "brief:6",
        "brief:7",
        "brief:8",
        "brief:9",
        "brief:off",
    ]
    update, msg = tap(ALLOWED, "brief:7")
    await bot.on_button(update, ctx)
    assert store.get_home(ALLOWED).brief_hour == 7 and last_reply(msg) == prompts.BRIEF_ON.format(
        time="7 am", place="Maplewood"
    )
    update, msg = message(ALLOWED, "/brief")
    await bot.cmd_brief(update, ctx)
    assert prompts.BRIEF_STATUS_ON.format(time="7 am", place="Maplewood") in last_reply(msg)
    for bad in ("brief:3", "brief:x", "brief:"):
        update, msg = tap(ALLOWED, bad)
        await bot.on_button(update, ctx)
        msg.reply_text.assert_not_awaited()
    assert store.get_home(ALLOWED).brief_hour == 7
    update, msg = tap(ALLOWED, "brief:off")
    await bot.on_button(update, ctx)
    assert store.get_home(ALLOWED).brief_hour is None and last_reply(msg) == prompts.BRIEF_OFF


async def test_brief_switches_are_closed_to_strangers(ctx, store):
    store.save_home(STRANGER, "Maplewood", MAPLEWOOD().id)
    update, _ = tap(STRANGER, "brief:7")
    await bot.on_button(update, ctx)
    assert store.get_home(STRANGER).brief_hour is None


def job_ctx(ctx, allowed=(ALLOWED,)):
    ctx.application.bot_data[bot.ALLOWED_KEY] = frozenset(allowed)
    ctx.bot = SimpleNamespace(send_message=AsyncMock())
    return ctx


@needs_kernel
async def test_morning_job_sends_once_a_day_at_the_local_hour(ctx, store, monkeypatch):
    ctx = job_ctx(ctx)
    store.save_home(ALLOWED, "Maplewood", MAPLEWOOD().id)
    store.set_brief(ALLOWED, 7)
    _save_pune(store)

    clock = {"now": datetime(2026, 11, 9, 12, 5, tzinfo=UTC)}  # 6:05 am in Minnesota: too early
    monkeypatch.setattr(bot, "_now", lambda: clock["now"])
    await bot._brief_job(ctx)
    ctx.bot.send_message.assert_not_awaited()

    clock["now"] = datetime(2026, 11, 9, 13, 5, tzinfo=UTC)  # 7:05 am
    await bot._brief_job(ctx)
    chat, text = ctx.bot.send_message.await_args.args
    assert chat == ALLOWED and "Good morning! Today is Monday, 09 November 2026." in text
    assert (
        "Traditionally avoided for starting new things: 08:15 to 09:28 (called Rahu Kaala), Maplewood" in text
    )
    assert "Shukla Pratipada" in text and "Tulu date:" in text and "dasha" not in text.lower()
    assert store.get_home(ALLOWED).brief_last == "2026-11-09"

    clock["now"] = datetime(2026, 11, 9, 13, 50, tzinfo=UTC)  # same morning: no repeat
    await bot._brief_job(ctx)
    assert ctx.bot.send_message.await_count == 1
    clock["now"] = datetime(2026, 11, 10, 13, 5, tzinfo=UTC)  # next morning
    await bot._brief_job(ctx)
    assert ctx.bot.send_message.await_count == 2


@needs_kernel
async def test_morning_job_works_without_saved_birth_details_and_skips_people_off_the_allowlist(
    ctx, store, monkeypatch
):
    ctx = job_ctx(ctx)
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, 13, 5, tzinfo=UTC))
    for chat in (ALLOWED, STRANGER):
        store.save_home(chat, "Maplewood", MAPLEWOOD().id)
        store.set_brief(chat, 7)
    await bot._brief_job(ctx)
    assert ctx.bot.send_message.await_count == 1
    chat, text = ctx.bot.send_message.await_args.args
    assert chat == ALLOWED and "dasha" not in text.lower() and "(called Rahu Kaala)" in text


@needs_kernel
async def test_one_failed_delivery_does_not_stop_the_others_or_leak_details(ctx, store, monkeypatch, caplog):
    other = 222
    ctx = job_ctx(ctx, allowed=(ALLOWED, other))
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, 13, 5, tzinfo=UTC))
    for chat in (ALLOWED, other):
        store.save_home(chat, "Maplewood", MAPLEWOOD().id)
        store.set_brief(chat, 7)
    ctx.bot.send_message.side_effect = [RuntimeError("secret Maplewood details"), None]
    with caplog.at_level(logging.ERROR, logger="samay"):
        await bot._brief_job(ctx)
    assert ctx.bot.send_message.await_count == 2
    assert "RuntimeError" in caplog.text and "secret" not in caplog.text
    assert store.get_home(ALLOWED).brief_last is None and store.get_home(other).brief_last == "2026-11-09"


def test_a_job_is_scheduled_when_the_scheduler_is_available(store):
    app = bot.build_application("123:abc", frozenset({1}), store)
    assert app.job_queue is not None and [j.name for j in app.job_queue.jobs()] == ["morning_brief"]


# --- grounded questions and answers ----------------------------------------------------------------

import yaml

from samay.engine import entries as entry_store


@needs_kernel
async def test_question_about_a_planet_quotes_the_checked_entry_and_adds_chart_facts(ctx, store, monkeypatch):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, tzinfo=UTC))
    _save_pune(store)
    update, msg = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    text = last_reply(msg)
    assert "Varahamihira describes Saturn as the sorrow of the cosmic person (Kalapurusha)." in text
    assert "Sources: Brihat Jataka 2.1, 20.1, 20.11 · checked" in text and "(translation-checked)" not in text
    assert "In your birth chart, Saturn is in Sagittarius (Dhanu), the 2nd house" in text
    assert store.top_misses() == []  # answered, so nothing to research


@needs_kernel
async def test_question_with_no_source_says_so_shows_facts_and_counts_only_the_topic(
    ctx, store, monkeypatch, empty_entries
):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, tzinfo=UTC))
    _save_pune(store)
    update, msg = message(ALLOWED, "what does my current dasha mean for me and my son's marriage?")
    await bot.on_text(update, ctx)
    text = last_reply(msg)
    assert (
        prompts.NO_SOURCE in text
        and "Your Jupiter chapter (dasha) lasts 16 years" in text
        and "you are in it now" in text
    )
    assert store.top_misses() == [("dasha:jupiter", 1)]
    with sqlite3.connect(store.path) as c:
        dump = "\n".join(c.iterdump())
    assert "marriage" not in dump and "son's" not in dump and "current dasha mean" not in dump


async def test_a_question_about_the_future_with_no_topic_is_declined_and_not_recorded(ctx, store):
    update, msg = message(ALLOWED, "will I win the lottery")
    await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.NO_TOPIC and store.top_misses() == []


async def test_without_birth_details_the_entry_is_still_shown_and_the_person_is_invited(ctx, store):
    update, msg = message(ALLOWED, "/ask")
    ctx.args = ["what", "is", "mars?"]
    await bot.cmd_ask(update, ctx)
    text = last_reply(msg)
    assert (
        "Mars as the strength" in text
        and prompts.NEED_BIRTH_FOR_FACTS in text
        and "From your chart" not in text
    )


async def test_ask_menu_and_bare_command_prompt_for_a_question(ctx):
    update, msg = message(ALLOWED, prompts.MENU_ASK)
    await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.ASK_QUESTION
    update, msg = message(ALLOWED, "/ask")
    ctx.args = []
    await bot.cmd_ask(update, ctx)
    assert last_reply(msg) == prompts.ASK_QUESTION


async def test_rahu_question_gets_its_sourced_names_and_the_astronomy_note(ctx, store):
    update, msg = message(ALLOWED, "what is rahu")
    await bot.on_text(update, ctx)
    text = last_reply(msg)
    assert "Moon's ascending node" in text and "Source: Brihat Jataka 2.3 · checked" in text
    assert "Moon's path crosses the Sun's path" in text and prompts.NO_SOURCE not in text
    assert store.top_misses() == []


async def test_answer_has_no_sanskrit_button_without_a_checked_verse(ctx):
    update, msg = message(
        ALLOWED, "what does my venus dasha mean"
    )  # Phaladeepika entries carry no verse text
    await bot.on_text(update, ctx)
    assert msg.reply_text.await_args.kwargs["reply_markup"] is bot.MENU


async def test_planet_answers_offer_the_sanskrit_view_and_label_the_typed_text(ctx):
    update, msg = message(ALLOWED, "what is venus")
    await bot.on_text(update, ctx)
    assert buttons_of(msg.reply_text.await_args.kwargs["reply_markup"]) == {
        prompts.BTN_MORE: "qa:full:planet:venus",
        prompts.BTN_SANSKRIT: "qa:sa:planet:venus",
    }
    update, msg = tap(ALLOWED, "qa:sa:planet:venus")
    update.callback_query.edit_message_text = AsyncMock()
    await bot.on_button(update, ctx)
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "मदनो" in text and "madano" in text  # verse 2.1: Venus is desire (madana)
    assert text.count(prompts.VERSE_UNPROOFREAD) == 1  # one note under all the verses shown (2.1 and 2.3)
    assert (
        "Varahamihira describes Venus as the desire" not in text
    )  # the English is swapped out, not added to


async def test_sanskrit_toggle_swaps_a_checked_verse_in_place(ctx, tmp_path, monkeypatch):
    entry = {
        "id": "t-venus",
        "topic": "planet:venus",
        "system": "any",
        "english": "English words.",
        "citation": {"text": "Test", "chapter": 1, "verse": 1, "edition": "test"},
        "verse": {"devanagari": "शुक्रः", "roman": "śukraḥ", "text_checked": True},
        "verification": {
            "level": "translation-checked",
            "checked_by": "t",
            "checked_on": "2026-11-09",
            "against": "test",
        },
    }
    (tmp_path / "e.yaml").write_text(yaml.safe_dump([entry], allow_unicode=True))
    monkeypatch.setattr(entry_store, "ENTRIES_DIR", tmp_path)
    entry_store.load_entries.cache_clear()
    try:
        update, msg = message(ALLOWED, "what is venus")
        await bot.on_text(update, ctx)
        assert "English words." in last_reply(msg)
        assert buttons_of(msg.reply_text.await_args.kwargs["reply_markup"]) == {
            prompts.BTN_SANSKRIT: "qa:sa:planet:venus"
        }

        update, msg = tap(ALLOWED, "qa:sa:planet:venus")
        update.callback_query.edit_message_text = AsyncMock()
        await bot.on_button(update, ctx)
        edit = update.callback_query.edit_message_text.await_args
        assert "शुक्रः\nśukraḥ" in edit.args[0] and "English words." not in edit.args[0]
        assert prompts.VERSE_UNPROOFREAD in edit.args[0]  # these test entries are not marked proofread
        assert buttons_of(edit.kwargs["reply_markup"]) == {prompts.BTN_ENGLISH: "qa:en:planet:venus"}
    finally:
        entry_store.load_entries.cache_clear()


async def test_bad_toggle_data_is_ignored(ctx):
    for data in ("qa:xx:planet:venus", "qa:sa:planet:pluto", "qa:sa:", "qa:"):
        update, msg = tap(ALLOWED, data)
        update.callback_query.edit_message_text = AsyncMock()
        await bot.on_button(update, ctx)
        update.callback_query.edit_message_text.assert_not_awaited()
        msg.reply_text.assert_not_awaited()


async def test_strangers_cannot_ask(ctx, store):
    update, msg = message(STRANGER, "what is saturn")
    await bot.on_text(update, ctx)
    msg.reply_text.assert_not_awaited()
    assert store.top_misses() == []


# --- One source-grounded, plain-language AI answer -------------------------------------------------

from samay import narrate, qa


@pytest.fixture
def ai_on(monkeypatch):
    """The model is on; its replies are scripted. cfg["sort"] answers the topic sorter, cfg["ai"] the open answer."""
    monkeypatch.setattr(narrate, "OLLAMA_URL", "http://ollama.test")
    cfg = {
        "sort": "planet:saturn",
        "ai": "Saturn is linked with discipline and patience in Jyotish.",
        "calls": [],
    }

    async def fake(
        system,
        prompt,
        client=None,
        model=None,
        timeout=None,
        max_tokens=None,
        temperature=None,
    ):
        cfg["calls"].append(
            {
                "system": system,
                "prompt": prompt,
                "model": model,
                "timeout": timeout,
                "temperature": temperature,
            }
        )
        return cfg["sort"] if system == qa.MODEL_SYSTEM else cfg["ai"]

    monkeypatch.setattr(narrate, "complete", fake)
    return cfg


def _texts(msg):
    return [c.args[0] for c in msg.reply_text.await_args_list]


async def test_ai_answer_uses_the_sources_as_context_and_is_the_only_response(ctx, ai_on):
    update, msg = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    (only,) = _texts(msg)
    assert only == (
        "Saturn is linked with discipline and patience in Jyotish.\n\n"
        "Source: Brihat Jataka 2.1 · checked\n\n"
        "Traditional Jyotish interpretation, for reflection and fun — not a guarantee of events."
    )
    call = next(c for c in ai_on["calls"] if c["system"] == qa.AI_SYSTEM)
    assert "Verified facts:" in call["prompt"]
    assert (
        "Checked source Brihat Jataka 2.1" in call["prompt"]
        and "sorrow of the cosmic person" in call["prompt"]
    )
    assert call["model"] == narrate.AI_MODEL and call["timeout"] == narrate.AI_TIMEOUT_SECONDS


async def test_long_ai_answer_is_delivered_complete_with_its_source(ctx, ai_on):
    ai_on["ai"] = "The text describes a period for reflection. " * 45 + "This is the complete conclusion."
    update, msg = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    (only,) = _texts(msg)
    assert only.startswith(ai_on["ai"] + "\n\n")
    assert "Source: Brihat Jataka 2.1 · checked" in only
    assert only.endswith(prompts.AI_CAVEAT)


async def test_the_ai_answers_what_the_sources_cannot(ctx, store, ai_on):
    ai_on["sort"], ai_on["ai"] = (
        "none",
        "A nakshatra is one of 27 divisions of the Moon's path.",
    )
    update, msg = message(ALLOWED, "what is a nakshatra?")
    await bot.on_text(update, ctx)
    (only,) = _texts(msg)
    assert only.startswith("A nakshatra is one of 27") and prompts.AI_CAVEAT in only
    assert store.top_misses() == []  # nothing was sorted into a topic, so nothing is counted


async def test_unsourced_topic_notes_it_for_research_and_the_ai_still_answers(
    ctx, store, ai_on, empty_entries
):
    ai_on["sort"] = "dasha:venus"
    ai_on["ai"] = "This is a general explanation."
    update, msg = message(ALLOWED, "what does my venus dasha mean")
    await bot.on_text(update, ctx)
    (only,) = _texts(msg)
    assert only.startswith(prompts.NO_SOURCE_AI + "\n\nThis is a general explanation.")
    assert only.endswith(prompts.AI_CAVEAT) and "AI says" not in only
    assert store.top_misses() == [("dasha:venus", 1)]


async def test_when_the_ai_fails_the_person_gets_one_source_based_fallback(ctx, ai_on):
    ai_on["ai"] = None
    update, msg = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    (only,) = _texts(msg)
    assert "Brihat Jataka 2.1" in only and prompts.AI_UNAVAILABLE in only


async def test_without_the_model_there_is_one_message_in_the_original_wording(ctx):
    update, msg = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    assert len(_texts(msg)) == 1 and "AI says" not in _texts(msg)[0]
    update, msg = message(ALLOWED, "what is a nakshatra?")
    await bot.on_text(update, ctx)
    assert _texts(msg) == [prompts.NO_TOPIC]


async def test_the_question_is_neither_stored_nor_logged(ctx, store, ai_on, caplog):
    update, _ = message(ALLOWED, "what does shani mean for my brother Raju in Wagholi?")
    with caplog.at_level(logging.DEBUG):
        await bot.on_text(update, ctx)
    with sqlite3.connect(store.path) as c:
        dump = "\n".join(c.iterdump())
    assert "Raju" not in dump and "Wagholi" not in dump and "Raju" not in caplog.text


async def test_strangers_get_no_ai_answer_and_cost_no_model_call(ctx, ai_on):
    update, msg = message(STRANGER, "what is saturn")
    await bot.on_text(update, ctx)
    msg.reply_text.assert_not_awaited()
    assert ai_on["calls"] == []


@needs_kernel
async def test_the_model_does_not_replace_the_plain_today_unless_rewording_is_switched_on(
    ctx, store, ai_on, monkeypatch
):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 9, 15, 0, tzinfo=UTC))
    _save_pune(store)
    update, msg = message(ALLOWED, "/today")
    await bot._command("today")(update, ctx)
    text = last_reply(msg)
    assert "period of life" in text and "Technical details" not in text
    assert not any(c["system"] == narrate.SYSTEM for c in ai_on["calls"])


# --- a repeated message is answered once ----------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(bot, "_monotonic", lambda: now["t"])
    return now


async def test_start_sent_twice_is_answered_once(ctx, clock, caplog):
    first, msg1 = message(ALLOWED, "/start")
    second, msg2 = message(ALLOWED, "/start")  # a second, separate message, as a client double-send would be
    with caplog.at_level(logging.INFO, logger="samay"):
        await bot.cmd_start(first, ctx)
        clock["t"] += 0.4
        await bot.cmd_start(second, ctx)
    assert msg1.reply_text.await_count == 1 and msg2.reply_text.await_count == 0
    assert (
        "ignored a repeated message" in caplog.text and "/start" not in caplog.text
    )  # no message text logged


async def test_the_same_command_works_again_after_the_window(ctx, clock):
    for _ in range(2):
        update, msg = message(ALLOWED, "/help")
        await bot.cmd_help(update, ctx)
        assert msg.reply_text.await_count == 1
        clock["t"] += bot.DEBOUNCE_SECONDS + 0.1


async def test_different_text_or_a_different_chat_is_never_suppressed(ctx, clock):
    ctx.application.bot_data[bot.ALLOWED_KEY] = frozenset({ALLOWED, 222})
    for chat, text, handler in (
        (ALLOWED, "/start", bot.cmd_start),
        (ALLOWED, "/help", bot.cmd_help),
        (222, "/start", bot.cmd_start),
    ):
        update, msg = message(chat, text)
        await handler(update, ctx)
        assert msg.reply_text.await_count == 1, (chat, text)


async def test_a_menu_button_that_calls_a_command_handler_is_not_mistaken_for_a_repeat(ctx, store, clock):
    update, msg = message(ALLOWED, prompts.MENU_FORGET)  # on_text -> cmd_forget, for the same update
    await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.FORGET_ASK
    again, msg2 = message(ALLOWED, prompts.MENU_FORGET)  # a double tap on the same button
    await bot.on_text(again, ctx)
    msg2.reply_text.assert_not_awaited()


async def test_a_double_tapped_question_is_answered_once(ctx, clock):
    for expected in (1, 0):
        update, msg = message(ALLOWED, "what does shani stand for")
        await bot.on_text(update, ctx)
        assert msg.reply_text.await_count == expected


async def test_strangers_are_not_remembered_so_they_cannot_block_the_owner(ctx, clock):
    stranger, _ = message(STRANGER, "/start")
    await bot.cmd_start(stranger, ctx)
    owner, msg = message(ALLOWED, "/start")
    await bot.cmd_start(owner, ctx)
    assert msg.reply_text.await_count == 1
    assert (STRANGER, "/start") not in ctx.application.bot_data.get(bot.RECENT_KEY, {})


async def test_old_entries_are_forgotten_so_the_memory_stays_small(ctx, clock):
    for i in range(50):
        update, _ = message(ALLOWED, f"/ask question {i}")
        await bot.on_text(update, ctx)
        clock["t"] += bot.DEBOUNCE_SECONDS + 0.1
    assert len(ctx.application.bot_data[bot.RECENT_KEY]) <= 1


# --- conversation: follow-ups, small talk, and what is (not) remembered -----------------------------------


def _router_prompts(cfg):
    return [c["prompt"] for c in cfg["calls"] if c["system"] == qa.MODEL_SYSTEM]


async def test_a_follow_up_is_routed_with_the_previous_topic_and_the_ai_sees_the_exchange(ctx, ai_on, clock):
    update, _ = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    clock["t"] += 10
    ai_on["sort"] = "planet:jupiter"
    ai_on["ai"] = "Jupiter is associated with wisdom."
    update, msg = message(ALLOWED, "and the other big one?")  # no keyword for the code to match
    await bot.on_text(update, ctx)
    assert "Previous topic: planet:saturn" in _router_prompts(ai_on)[1]
    prompt = [c["prompt"] for c in ai_on["calls"] if c["system"] == qa.AI_SYSTEM][1]
    assert "Person: What does Shani stand for?\nYou: Saturn is linked with discipline" in prompt
    assert "Jupiter" in _texts(msg)[0]


async def test_small_talk_gets_only_the_models_reply_and_is_not_counted_as_a_miss(ctx, store, ai_on, clock):
    ai_on["sort"], ai_on["ai"] = (
        "none",
        "Namaste! Ask me about a planet, a house or your current period.",
    )
    update, msg = message(ALLOWED, "hello, how are you?")
    await bot.on_text(update, ctx)
    (only,) = _texts(msg)
    assert only.startswith("Namaste!") and store.top_misses() == []


async def test_small_talk_when_the_model_is_down_gets_the_plain_decline(ctx, ai_on, clock):
    ai_on["sort"], ai_on["ai"] = "none", None
    update, msg = message(ALLOWED, "hello")
    await bot.on_text(update, ctx)
    assert _texts(msg) == [prompts.NO_TOPIC + "\n\n" + prompts.AI_UNAVAILABLE]


async def test_the_conversation_is_remembered_for_a_few_turns_then_forgotten(ctx, ai_on, clock):
    for i in range(6):
        update, _ = message(ALLOWED, f"question number {i}")
        await bot.on_text(update, ctx)
        clock["t"] += 10
    assert len(bot._recent_turns(ctx, ALLOWED)) == bot.CHAT_TURNS
    clock["t"] += bot.CHAT_TTL_SECONDS + 1
    assert bot._recent_turns(ctx, ALLOWED) == []


async def test_forgetting_me_clears_the_remembered_conversation(ctx, store, ai_on, clock):
    update, _ = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    assert bot._recent_turns(ctx, ALLOWED)
    update, _ = tap(ALLOWED, bot.FORGET_YES)
    await bot.on_button(update, ctx)
    assert bot._recent_turns(ctx, ALLOWED) == []


async def test_the_conversation_exists_only_in_memory(ctx, store, ai_on, clock, caplog):
    update, _ = message(ALLOWED, "my cousin Raju asked about shani")
    with caplog.at_level(logging.DEBUG):
        await bot.on_text(update, ctx)
    with sqlite3.connect(store.path) as c:
        assert "Raju" not in "\n".join(c.iterdump())
    assert "Raju" not in caplog.text and bot._recent_turns(ctx, ALLOWED)


async def test_without_the_model_nothing_is_remembered(ctx, clock):
    update, _ = message(ALLOWED, "What does Shani stand for?")
    await bot.on_text(update, ctx)
    assert bot._recent_turns(ctx, ALLOWED) == []


async def test_more_and_less_buttons_switch_the_answer_in_place(ctx):
    update, _ = tap(ALLOWED, "qa:full:planet:venus")
    update.callback_query.edit_message_text = AsyncMock()
    await bot.on_button(update, ctx)
    edit = update.callback_query.edit_message_text.await_args
    assert edit.args[0].count("• Varahamihira") >= 4 and "tr. N. Chidambaram Iyer" in edit.args[0]
    assert buttons_of(edit.kwargs["reply_markup"]) == {
        prompts.BTN_LESS: "qa:en:planet:venus",
        prompts.BTN_SANSKRIT: "qa:sa:planet:venus",
    }
    update, _ = tap(ALLOWED, "qa:en:planet:venus")
    update.callback_query.edit_message_text = AsyncMock()
    await bot.on_button(update, ctx)
    compact = update.callback_query.edit_message_text.await_args
    assert compact.args[0].count("Varahamihira") == 1
    assert prompts.BTN_MORE in buttons_of(compact.kwargs["reply_markup"])


# --- "typing..." while the bot works ---------------------------------------------------------------------


def _chat_with_actions(chat_id=ALLOWED):
    return SimpleNamespace(id=chat_id, send_action=AsyncMock())


async def test_typing_is_shown_while_the_block_runs_and_stops_afterwards(monkeypatch):
    monkeypatch.setattr(bot, "TYPING_REFRESH_SECONDS", 0.01)
    chat = _chat_with_actions()
    update = SimpleNamespace(effective_chat=chat)
    async with bot.typing(update):
        for _ in range(
            200
        ):  # wait for the refreshes (not a fixed sleep: a busy CI runner can be slow to schedule them)
            if chat.send_action.await_count >= 2:
                break
            await asyncio.sleep(0.01)
    calls_while_running = chat.send_action.await_count
    assert calls_while_running >= 2 and chat.send_action.await_args.args[0] == bot.ChatAction.TYPING
    await asyncio.sleep(0.05)
    assert chat.send_action.await_count == calls_while_running  # cancelled when the block ended


async def test_a_failing_typing_hint_never_breaks_the_reply(monkeypatch):
    monkeypatch.setattr(bot, "TYPING_REFRESH_SECONDS", 0.01)
    chat = _chat_with_actions()
    chat.send_action.side_effect = RuntimeError("network")
    async with bot.typing(SimpleNamespace(effective_chat=chat)):
        await asyncio.sleep(0.03)  # no exception escapes


async def test_typing_does_nothing_when_the_chat_cannot_show_it():
    async with bot.typing(SimpleNamespace(effective_chat=SimpleNamespace(id=1))):
        pass


async def test_the_chat_shows_typing_while_the_model_thinks(ctx, ai_on, clock, monkeypatch):
    monkeypatch.setattr(bot, "TYPING_REFRESH_SECONDS", 0.01)
    update, msg = message(ALLOWED, "What does Shani stand for?")
    update.effective_chat = _chat_with_actions()
    real = ai_on["calls"]

    async def slow(
        system,
        prompt,
        client=None,
        model=None,
        timeout=None,
        max_tokens=None,
        temperature=None,
    ):
        real.append(
            {
                "system": system,
                "prompt": prompt,
                "model": model,
                "timeout": timeout,
                "temperature": temperature,
            }
        )
        await asyncio.sleep(0.05)
        return "planet:saturn" if system == qa.MODEL_SYSTEM else "A slow answer."

    monkeypatch.setattr(narrate, "complete", slow)
    await bot.on_text(update, ctx)
    assert update.effective_chat.send_action.await_count >= 2
    assert _texts(msg) == ["A slow answer.\n\nSource: Brihat Jataka 2.1 · checked\n\n" + prompts.AI_CAVEAT]


async def test_no_typing_is_shown_when_the_model_is_off(ctx, clock):
    update, _ = message(ALLOWED, "What does Shani stand for?")
    update.effective_chat = _chat_with_actions()
    await bot.on_text(update, ctx)
    update.effective_chat.send_action.assert_not_awaited()


async def test_a_tap_too_old_to_acknowledge_is_still_handled_but_other_errors_are_not(ctx, store):
    from telegram.error import BadRequest

    _save_pune(store)
    update, _ = tap(ALLOWED, "img:north:0")
    update.callback_query.answer.side_effect = BadRequest("Query is too old and response timeout expired")
    await bot.on_button(update, ctx)  # the tap waited behind a slow model call: the button still works
    update.callback_query.edit_message_media.assert_awaited()
    update.callback_query.answer.side_effect = BadRequest("Chat not found")
    with pytest.raises(BadRequest):
        await bot.on_button(update, ctx)


async def test_a_tap_is_answered_while_the_same_chat_waits_on_a_slow_message(ctx, store, monkeypatch):
    import asyncio

    _save_pune(store)
    release = asyncio.Event()

    async def slow(update, ctx_):
        await release.wait()

    slow_handler = bot.guarded(slow)
    msg_update, _ = message(ALLOWED, "hello")
    first = asyncio.create_task(slow_handler(msg_update, ctx))
    second = asyncio.create_task(slow_handler(message(ALLOWED, "again")[0], ctx))
    await asyncio.sleep(0)
    tap_update, _ = tap(ALLOWED, "img:north:0")
    await asyncio.wait_for(
        bot.on_button(tap_update, ctx), timeout=5
    )  # not blocked by the two waiting messages
    tap_update.callback_query.edit_message_media.assert_awaited()
    assert not second.done()  # messages in one chat stay in order
    release.set()
    await asyncio.gather(first, second)


@needs_kernel
async def test_a_question_about_the_week_ahead_gets_the_outlook_with_more_and_is_not_a_miss(
    ctx, store, monkeypatch
):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 12, 6, tzinfo=UTC))
    _save_pune(store)
    update, msg = message(ALLOWED, "What does my upcoming week look like")
    await bot.on_text(update, ctx)
    text = last_reply(msg)
    assert "🔮 Your week ahead" in text and "The Moon changes house every couple of days" in text
    assert "house" not in text.split("Tap")[0].replace("changes house", "").replace(
        "change house", ""
    )  # no houses, points or verses in plain words
    assert [b.text for b in last_buttons(msg)] == [prompts.BTN_TECH]
    assert store.top_misses() == []
    tap_update, _ = tap(ALLOWED, last_buttons(msg)[0].callback_data)
    tap_update.callback_query.edit_message_text = AsyncMock()
    await bot.on_button(tap_update, ctx)
    shown = tap_update.callback_query.edit_message_text.await_args
    assert "🌙 Moon" in shown.args[0] and "Counted from your Moon sign" in shown.args[0]  # the technical view
    assert [b.text for b in shown.kwargs["reply_markup"].inline_keyboard[0]] == [prompts.BTN_PLAIN]


async def test_a_reply_over_telegrams_limit_is_sent_in_parts_with_the_buttons_on_the_last(
    ctx,
):
    update, msg = message(ALLOWED, "x")
    long_text = "\n\n".join(f"block {i} " + "word " * 300 for i in range(8))
    await bot._say(update, long_text, "BUTTONS")
    sent = [c.args[0] for c in msg.reply_text.await_args_list]
    assert len(sent) > 1 and all(len(s) <= 4096 for s in sent)
    assert all("reply_markup" not in c.kwargs for c in msg.reply_text.await_args_list[:-1])
    assert msg.reply_text.await_args_list[-1].kwargs["reply_markup"] == "BUTTONS"


@needs_kernel
async def test_a_question_that_looks_ahead_gets_one_labelled_forward_looking_ai_reading(
    ctx, store, ai_on, monkeypatch
):
    # Owner's decision (2026-11-24): a coming day, week, month or year may get an informed reading from the model,
    # grounded in the supplied facts and labelled as an AI reading, not a guarantee.
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 12, 6, tzinfo=UTC))
    _save_pune(store)
    ai_on["sort"] = "future:week"
    ai_on["ai"] = "The week tends to favour steady work."
    update, msg = message(ALLOWED, "what will my week be like")
    await bot.on_text(update, ctx)
    (last,) = _texts(msg)
    assert prompts.NO_SOURCE_AI in last and "The week tends to favour steady work." in last
    assert last.endswith(prompts.AI_FORECAST_CAVEAT)
    system = next(c["system"] for c in ai_on["calls"] if c["system"] != qa.MODEL_SYSTEM)
    assert system == qa.AI_FORECAST_SYSTEM and "informed, forward-looking reading" in system
    assert "do not present anything as likely, expected, or a prediction" not in system


@needs_kernel
async def test_my_day_tomorrow_gets_an_ai_reading_from_the_day_s_facts_at_home(
    ctx, store, ai_on, monkeypatch
):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 24, 1, 30, tzinfo=UTC))  # 07:00 in Pune
    _save_pune(store)
    pune = geo.find_places("Pune")[0]
    store.save_home(ALLOWED, "Pune", pune.id)
    ai_on["sort"] = "future:tomorrow"
    ai_on["ai"] = "Tomorrow tends to favour quiet, steady work."
    update, msg = message(ALLOWED, "What does my day look like tomorrow")
    await bot.on_text(update, ctx)
    (last,) = _texts(msg)
    assert "Tomorrow tends to favour quiet, steady work." in last and last.endswith(
        prompts.AI_FORECAST_CAVEAT
    )
    call = next(c for c in ai_on["calls"] if c["system"] != qa.MODEL_SYSTEM)
    assert call["system"] == qa.AI_FORECAST_SYSTEM
    assert "Wednesday 25 Nov 2026" in call["prompt"] and "Rahu Kaala" in call["prompt"]
    assert "tithi" in call["prompt"] and "Pune" in call["prompt"]


@needs_kernel
async def test_my_day_with_the_model_off_is_the_sourced_answer_and_no_model_is_asked(ctx, store, monkeypatch):
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 24, 1, 30, tzinfo=UTC))
    calls = []

    async def never(*a, **k):
        calls.append(a)
        return "should not be used"

    monkeypatch.setattr(qa.narrate, "complete", never)
    monkeypatch.setattr(qa.narrate, "OLLAMA_URL", "")
    _save_pune(store)
    store.save_home(ALLOWED, "Pune", geo.find_places("Pune")[0].id)
    update, msg = message(ALLOWED, "What does my day look like tomorrow")
    await bot.on_text(update, ctx)
    (last,) = _texts(msg)
    assert last.startswith("🔮 Your day tomorrow: Wednesday 25 Nov 2026") and "Rahu Kaala" in last
    assert calls == [] and "AI" not in last


async def test_my_day_without_saved_birth_details_asks_for_them(ctx, store, ai_on):
    ai_on["sort"] = "future:tomorrow"
    update, msg = message(ALLOWED, "What does my day look like tomorrow")
    await bot.on_text(update, ctx)
    assert _texts(msg)[-1] == prompts.NEED_BIRTH_FOR_FUTURE
    assert all(
        c["system"] == qa.MODEL_SYSTEM for c in ai_on["calls"]
    )  # only the router; no reading without a birth


async def test_my_day_without_saved_birth_details_and_the_model_off_asks_for_them(ctx, store):
    update, msg = message(ALLOWED, "how will my day be")
    await bot.on_text(update, ctx)
    assert _texts(msg)[-1] == prompts.NEED_BIRTH_FOR_FUTURE


def test_only_looking_ahead_topics_are_predictions_and_sensitive_ones_never_reach_the_model():
    from samay.subject import Subject

    a = lambda topic, who=qa.SELF: qa.Answer(topic, (), (), who=who)
    assert (
        qa.is_prediction(a("future:week"))
        and qa.is_prediction(a("when:marriage"))
        and qa.is_prediction(a("life:career"))
    )
    assert not qa.is_prediction(a("planet:saturn")) and not qa.is_prediction(a(None))
    assert not qa.is_prediction(a("chart:longevity")) and not qa.is_prediction(a("chart:death_timing"))
    assert qa.is_prediction(
        a("life:career", Subject("Maya", "daughter", True))
    )  # a child's life area is still gentle, not gated


@needs_kernel
def test_the_morning_message_keeps_the_date_and_avoid_window_when_the_panchang_fails(monkeypatch, caplog):
    def broken(*_a, **_k):
        raise RuntimeError("secret Maplewood details")

    monkeypatch.setattr(bot.service, "panchang_report", broken)
    with caplog.at_level(logging.ERROR, logger="samay"):
        text = bot.compose_brief(None, MAPLEWOOD(), datetime(2026, 11, 9, 13, 5, tzinfo=UTC))
    assert "Good morning! Today is Monday, 09 November 2026." in text and "Tulu date" not in text
    assert (
        "Traditionally avoided for starting new things: 08:15 to 09:28 (called Rahu Kaala), Maplewood" in text
    )
    assert "panchang report failed error=RuntimeError" in caplog.text and "secret" not in caplog.text


# --- panchang questions -------------------------------------------------------------------------

from samay.render import panchang as panchang_words

PUNE_HOME = lambda: geo.find_places("Pune, IN")[0]


@pytest.fixture
def no_router(monkeypatch):
    """Panchang questions must be answered without the birth-chart router."""

    def refuse(*_a, **_k):
        raise AssertionError("the birth-chart router was called")

    monkeypatch.setattr(qa, "route_with_model", refuse)
    monkeypatch.setattr(qa, "rule_route", refuse)


@needs_kernel
async def test_a_panchang_question_is_answered_for_the_saved_home_without_the_router(
    ctx, store, monkeypatch, no_router
):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 21, 4, 0, tzinfo=UTC))
    store.save_home(ALLOWED, "Pune", PUNE_HOME().id)
    update, msg = message(ALLOWED, "what tithi today")
    await bot.on_text(update, ctx)
    text = last_reply(msg)
    assert "Tulu date" in text and "in Pune" in text and "Shukla Dwadashi" in text
    assert msg.reply_text.await_args.kwargs["reply_markup"] is bot.MENU


async def test_a_panchang_question_without_a_home_asks_for_the_city(ctx, store, monkeypatch, no_router):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    update, msg = message(ALLOWED, "is it ekadashi today")
    await bot.on_text(update, ctx)
    text = last_reply(msg)
    assert text.startswith(panchang_words.NEED_PLACE) and prompts.ASK_HOME in text
    assert store.get_draft(ALLOWED)["purpose"] == "home"


async def test_a_question_about_a_planet_still_reaches_the_birth_chart_router(ctx, monkeypatch):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    seen = []
    real = qa.rule_route
    monkeypatch.setattr(qa, "rule_route", lambda q, *a, **k: seen.append(q) or real(q, *a, **k))
    update, msg = message(ALLOWED, "tell me about Jupiter")
    await bot.on_text(update, ctx)
    assert seen == ["tell me about Jupiter"] and "Jupiter" in last_reply(msg)


@needs_kernel
async def test_a_list_of_observance_days_this_month_is_answered_in_lines(ctx, store, monkeypatch, no_router):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 22, 4, 0, tzinfo=UTC))
    store.save_home(ALLOWED, "Pune", PUNE_HOME().id)
    update, msg = message(ALLOWED, "list all auspicious days this month")
    await bot.on_text(update, ctx)
    (text,) = [c.args[0] for c in msg.reply_text.await_args_list]  # a month is quick: no "one moment" first
    assert text.splitlines()[0].startswith("Observance days from Sun 1 Nov to Mon 30 Nov 2026 in Pune")
    assert "Fri 20 Nov: Ekadashi" in text and "auspicious" not in text.lower()
    assert msg.reply_text.await_args.kwargs["reply_markup"] is bot.MENU


@needs_kernel
async def test_a_years_list_says_one_moment_first_and_arrives_in_safe_parts(
    ctx, store, monkeypatch, no_router
):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    monkeypatch.setattr(bot, "_now", lambda: datetime(2026, 11, 22, 4, 0, tzinfo=UTC))
    store.save_home(ALLOWED, "Pune", PUNE_HOME().id)
    update, msg = message(ALLOWED, "list all observance days for 2027")
    await bot.on_text(update, ctx)
    sent = [c.args[0] for c in msg.reply_text.await_args_list]
    assert sent[0] == panchang_words.WORKING and len(sent) >= 2 and all(len(s) <= 4096 for s in sent)
    body = "\n".join(sent[1:])
    assert body.startswith("Observance days from Fri 1 Jan to Fri 31 Dec 2027 in Pune")
    assert "January 2027" in body and "December 2027" in body and body.rstrip().endswith(".")
    assert msg.reply_text.await_args.kwargs["reply_markup"] is bot.MENU
