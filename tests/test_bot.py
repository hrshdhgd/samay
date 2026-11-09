"""Bot adapter: allowlist, wiring, persistence and logging. Handlers are driven with stub updates."""
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from samay.bot import app as bot
from samay.engine.paths import EPHEMERIS_PATH
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


def message(chat_id: int, text: str):
    msg = SimpleNamespace(text=text, reply_text=AsyncMock(), reply_photo=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=msg,
                           callback_query=None), msg


def tap(chat_id: int, data: str):
    msg = SimpleNamespace(text=None, reply_text=AsyncMock(), reply_photo=AsyncMock())
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_media=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=msg,
                           callback_query=query), msg


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
    env.write_text("# comment\nALLOWED_CHAT_IDS=5, 6\nSAMAY_TEST_KEY='quoted'\nSAMAY_TEST_SET=from-file\n\nbad line\n")
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
    monkeypatch.setattr(bot, "build_application", lambda *a: (_ for _ in ()).throw(RuntimeError("reached")))
    with pytest.raises(RuntimeError, match="reached"):
        bot.main()


def test_application_registers_every_command(store):
    app = bot.build_application("123:abc", frozenset({1}), store)
    commands = {c for group in app.handlers.values() for h in group for c in getattr(h, "commands", ())}
    assert commands == {"start", "help", "birth", "forget", "chart", "dasha", "today"}


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
    assert texts[0] == prompts.SAVED and texts[1].startswith("Lagna:")
    assert "Bombay Time" in texts[1]  # the caution that matters for a 1952 Indian birth
    assert "samay dev" not in texts[1] and "confidence:" not in texts[1] and "Profile:" not in texts[1]


async def test_draft_survives_a_restart(ctx, store):
    update, _ = message(ALLOWED, "/birth")
    await bot.cmd_birth(update, ctx)
    update, _ = message(ALLOWED, "15-08-1952")
    await bot.on_text(update, ctx)

    restarted = SimpleNamespace(application=SimpleNamespace(
        bot_data={bot.STORE_KEY: Store(store.path), bot.ALLOWED_KEY: frozenset({ALLOWED})}))
    update, msg = message(ALLOWED, "18:30")
    await bot.on_text(update, restarted)
    assert last_reply(msg) == prompts.ASK_PLACE


async def test_stale_button_after_restart_offers_a_fresh_start(ctx):
    update, msg = tap(ALLOWED, "dead|am")
    await bot.on_button(update, ctx)
    assert last_reply(msg) == prompts.STALE
    assert last_buttons(msg)[0].callback_data == "new"


async def test_text_without_a_conversation_points_to_the_menu(ctx):
    update, msg = message(ALLOWED, "namaste")
    await bot.on_text(update, ctx)
    assert last_reply(msg) == prompts.UNKNOWN_TEXT


async def test_asking_for_a_chart_without_details_starts_the_conversation(ctx, store):
    update, msg = message(ALLOWED, prompts.MENU_CHART)
    await bot.on_text(update, ctx)
    assert last_reply(msg).startswith(prompts.NEED_BIRTH) and store.get_draft(ALLOWED) is not None


async def test_forget_asks_first_then_deletes_everything(ctx, store):
    from samay.models import BirthInput

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
    assert menu[0].description == prompts.COMMANDS["chart"]


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
        "🔄 North Indian": "img:north:0", "🔢 Show degrees": "img:south:1"}
    assert buttons_of(bot.chart_markup("north", True)) == {
        "🔄 South Indian": "img:south:1", "🔢 Hide degrees": "img:north:0"}


def _save_pune(store):
    from samay.models import BirthInput

    store.save_user(ALLOWED, BirthInput("1990-08-15", "14:30", "Pune"))


@needs_kernel
async def test_my_chart_sends_the_south_picture_first_then_the_text(ctx, store):
    _save_pune(store)
    update, msg = message(ALLOWED, prompts.MENU_CHART)
    await bot.on_text(update, ctx)
    photo = msg.reply_photo.await_args
    assert photo.kwargs["photo"][:8] == b"\x89PNG\r\n\x1a\n"
    assert buttons_of(photo.kwargs["reply_markup"]) == buttons_of(bot.chart_markup("south", False))
    assert last_reply(msg).startswith("Lagna:")  # the text comes as its own message


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
        pictures.add(update.callback_query.edit_message_media.await_args.kwargs["media"].media.input_file_content)
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
