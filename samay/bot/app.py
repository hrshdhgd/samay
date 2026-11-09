"""Telegram adapter: allowlist, handlers, persisted drafts. All logic lives in flow/service/render.

Long polling, so no inbound port or TLS. Synchronous work runs in a worker thread. Logs carry
chat ids and error types only, never birth details.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .. import narrate, service
from ..engine.errors import SamayError
from ..models import NeedsDisambiguation
from ..render import prompts
from ..render.chart_image import STYLES, render_chart_png
from ..render.text import render_chart, render_dasha, render_today, today_facts
from ..store import Store
from . import flow

log = logging.getLogger("samay")
STORE_KEY, ALLOWED_KEY = "store", "allowed"
FORGET_YES, FORGET_NO = "forget:yes", "forget:no"
CHART_PREFIX = "img:"  # img:<south|north>:<0|1 = degrees shown>
NETWORK_TIMEOUT = 20.0  # seconds
MENU = ReplyKeyboardMarkup([list(row) for row in prompts.MENU_ROWS], resize_keyboard=True)


def parse_allowed(text: str) -> frozenset[int]:
    try:
        ids = frozenset(int(p) for p in text.replace(" ", "").split(",") if p)
    except ValueError:
        raise SystemExit("ALLOWED_CHAT_IDS must be comma-separated numbers") from None
    if not ids:
        raise SystemExit("ALLOWED_CHAT_IDS is empty: refusing to start an open bot")
    return ids


def _keyboard(reply: flow.Reply) -> InlineKeyboardMarkup | None:
    if not reply.buttons:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.label, callback_data=b.data) for b in row] for row in reply.buttons]
    )


def chart_markup(style: str, degrees: bool) -> InlineKeyboardMarkup:
    """The two switches under the chart picture: South/North style and degrees on/off."""
    other = "north" if style == "south" else "south"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🔄 {other.title()} Indian", callback_data=f"{CHART_PREFIX}{other}:{int(degrees)}"),
        InlineKeyboardButton("🔢 Hide degrees" if degrees else "🔢 Show degrees",
                             callback_data=f"{CHART_PREFIX}{style}:{int(not degrees)}"),
    ]])


def guarded(handler):
    """Ignore, silently, anyone who is not on the allowlist."""

    @functools.wraps(handler)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat is None or chat.id not in ctx.application.bot_data[ALLOWED_KEY]:
            return None
        return await handler(update, ctx)

    return wrapper


def _store(ctx) -> Store:
    return ctx.application.bot_data[STORE_KEY]


async def _say(update: Update, text: str, markup=None) -> None:
    message = update.effective_message
    await message.reply_text(text, reply_markup=markup)


async def _send_flow(update: Update, ctx, chat_id: int, out: flow.Outcome, prefix: str = "") -> None:
    store = _store(ctx)
    if out.draft is not None:
        await asyncio.to_thread(store.save_draft, chat_id, out.draft.to_dict())
    if out.done is not None:
        await asyncio.to_thread(store.save_user, chat_id, out.done)
        await asyncio.to_thread(store.delete_draft, chat_id)
        await _say(update, out.reply.text, MENU)
        await _show(update, ctx, chat_id, "chart")
        return
    await _say(update, prefix + out.reply.text, _keyboard(out.reply))


async def _begin(update: Update, ctx, chat_id: int, prefix: str = "") -> None:
    await _send_flow(update, ctx, chat_id, flow.begin(), prefix)


async def _show(update: Update, ctx, chat_id: int, kind: str) -> None:
    saved = await asyncio.to_thread(_store(ctx).get_user, chat_id)
    if saved is None:
        await _begin(update, ctx, chat_id, prompts.NEED_BIRTH + "\n\n")
        return
    resolved = await asyncio.to_thread(service.resolve_birth, saved)
    if isinstance(resolved, NeedsDisambiguation):
        await _begin(update, ctx, chat_id, prompts.CHANGED + "\n\n")
        return
    now = datetime.now(UTC)
    if kind == "today":
        report = await asyncio.to_thread(service.today_report, resolved, now)
        reading = await narrate.narrate(today_facts(report)) if narrate.enabled() else None
        text = render_today(report, reading, technical=False)
    else:
        natal = await asyncio.to_thread(service.natal_report, resolved)
        if kind == "chart":
            picture = await asyncio.to_thread(render_chart_png, natal, "south", False)
            await update.effective_message.reply_photo(photo=picture, reply_markup=chart_markup("south", False))
        text = render_dasha(natal, now, technical=False) if kind == "dasha" else render_chart(natal, technical=False)
    await _say(update, text, MENU)


@guarded
async def cmd_start(update: Update, ctx) -> None:
    await _say(update, prompts.WELCOME, MENU)


@guarded
async def cmd_help(update: Update, ctx) -> None:
    await _say(update, prompts.help_text(), MENU)


@guarded
async def cmd_birth(update: Update, ctx) -> None:
    await _begin(update, ctx, update.effective_chat.id)


@guarded
async def cmd_forget(update: Update, ctx) -> None:
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(prompts.BTN_YES_DELETE, callback_data=FORGET_YES),
        InlineKeyboardButton(prompts.BTN_NO, callback_data=FORGET_NO),
    ]])
    await _say(update, prompts.FORGET_ASK, markup)


def _command(kind: str):
    @guarded
    async def handler(update: Update, ctx) -> None:
        await _show(update, ctx, update.effective_chat.id, kind)

    return handler


@guarded
async def on_text(update: Update, ctx) -> None:
    chat_id, text = update.effective_chat.id, update.effective_message.text or ""
    store = _store(ctx)
    await asyncio.to_thread(store.purge_expired)
    shortcuts = {
        prompts.MENU_CHART: lambda: _show(update, ctx, chat_id, "chart"),
        prompts.MENU_DASHA: lambda: _show(update, ctx, chat_id, "dasha"),
        prompts.MENU_TODAY: lambda: _show(update, ctx, chat_id, "today"),
        prompts.MENU_CHANGE: lambda: _begin(update, ctx, chat_id),
        prompts.MENU_FORGET: lambda: cmd_forget(update, ctx),
    }
    if text in shortcuts:
        await shortcuts[text]()
        return
    stored = await asyncio.to_thread(store.get_draft, chat_id)
    if stored is None:
        await _say(update, prompts.UNKNOWN_TEXT, MENU)
        return
    out = await asyncio.to_thread(flow.on_text, flow.Draft.from_dict(stored), text)
    await _send_flow(update, ctx, chat_id, out)


async def _redraw_chart(update: Update, ctx, chat_id: int, choice: str) -> None:
    """Swap the picture in place for the requested style and degrees setting."""
    style, _, degrees = choice.partition(":")
    if style not in STYLES or degrees not in ("0", "1"):
        return
    saved = await asyncio.to_thread(_store(ctx).get_user, chat_id)
    resolved = await asyncio.to_thread(service.resolve_birth, saved) if saved else None
    if resolved is None or isinstance(resolved, NeedsDisambiguation):
        await _say(update, prompts.NEED_BIRTH)
        return
    natal = await asyncio.to_thread(service.natal_report, resolved)
    picture = await asyncio.to_thread(render_chart_png, natal, style, degrees == "1")
    try:
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(picture), reply_markup=chart_markup(style, degrees == "1")
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():  # a double tap asks for the picture already shown
            raise


@guarded
async def on_button(update: Update, ctx) -> None:
    query = update.callback_query
    await query.answer()
    chat_id, data = update.effective_chat.id, query.data or ""
    if data.startswith(CHART_PREFIX):
        await _redraw_chart(update, ctx, chat_id, data[len(CHART_PREFIX):])
        return
    if data in (FORGET_YES, FORGET_NO):
        if data == FORGET_YES:
            await asyncio.to_thread(_store(ctx).forget, chat_id)
        await _say(update, prompts.FORGOTTEN if data == FORGET_YES else prompts.KEPT, MENU)
        return
    stored = await asyncio.to_thread(_store(ctx).get_draft, chat_id)
    draft = flow.Draft.from_dict(stored) if stored else None
    out = await asyncio.to_thread(flow.on_button, draft, data)
    await _send_flow(update, ctx, chat_id, out)


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    err = ctx.error
    chat = getattr(update, "effective_chat", None)
    kind = "expected" if isinstance(err, SamayError) else "unexpected"
    # Never log the exception text or traceback: they can contain birth details.
    log.error("handler failed (%s) chat=%s error=%s", kind, getattr(chat, "id", None), type(err).__name__)
    message = getattr(update, "effective_message", None)
    if message is not None:
        try:
            await message.reply_text(prompts.GENERIC_ERROR)
        except Exception as e:  # noqa: BLE001
            log.error("could not send the error notice: %s", type(e).__name__)


async def _register_commands(app) -> None:
    """Fill Telegram's "/" menu from the handlers that are really registered, in prompts.COMMANDS
    order, so a new command can never be missing from the menu or left in it by mistake."""
    live = {c for h in app.handlers.get(0, []) if isinstance(h, CommandHandler) for c in h.commands}
    unlisted = live - prompts.COMMANDS.keys()
    if unlisted:
        raise RuntimeError(f"commands without a description in prompts.COMMANDS: {sorted(unlisted)}")
    menu = [BotCommand(cmd, desc) for cmd, desc in prompts.COMMANDS.items() if cmd in live]
    await app.bot.set_my_commands(menu)
    log.info("registered %d commands in the Telegram menu", len(menu))


async def _post_init(app: Application) -> None:
    stamp = await asyncio.to_thread(service.warm)
    log.info("samay ready: ref %s = %s", stamp.code(), stamp.short())
    await _register_commands(app)


async def _post_shutdown(app: Application) -> None:
    await narrate.close()


def build_application(token: str, allowed: frozenset[int], store: Store) -> Application:
    app = (
        Application.builder()
        .token(token)
        # PTB's 5 s defaults are too tight for a slow or flaky connection.
        .connect_timeout(NETWORK_TIMEOUT)
        .read_timeout(NETWORK_TIMEOUT)
        .write_timeout(NETWORK_TIMEOUT)
        .pool_timeout(NETWORK_TIMEOUT)
        .get_updates_connect_timeout(NETWORK_TIMEOUT)
        .get_updates_read_timeout(NETWORK_TIMEOUT)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data[STORE_KEY], app.bot_data[ALLOWED_KEY] = store, allowed
    for name, fn in [("start", cmd_start), ("help", cmd_help), ("birth", cmd_birth), ("forget", cmd_forget),
                     ("chart", _command("chart")), ("dasha", _command("dasha")), ("today", _command("today"))]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    return app


def load_env_file(path: Path) -> None:
    """Add KEY=VALUE lines from a .env file to the environment; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # their INFO lines include the bot token
    load_env_file(Path(os.environ.get("SAMAY_ENV_FILE", ".env")))
    allowed = parse_allowed(os.environ.get("ALLOWED_CHAT_IDS", ""))
    token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("SAMAY_TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Set TELEGRAM_TOKEN (or SAMAY_TELEGRAM_BOT_TOKEN) to the token from @BotFather")
    app = build_application(token, allowed, Store())
    log.info("samay starting (long polling, %d allowed chat(s))", len(allowed))
    # bootstrap_retries=-1: keep retrying the first connection instead of exiting if Telegram is
    # briefly unreachable.
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY], bootstrap_retries=-1)
