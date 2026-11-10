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
from zoneinfo import ZoneInfo

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest, InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .. import narrate, qa, service
from ..engine import geo
from ..engine.errors import SamayError
from ..models import BirthInput, NeedsDisambiguation, ResolvedBirth
from ..render import prompts
from ..render.chart_image import STYLES, render_chart_png
from ..render.text import (
    render_answer,
    render_brief,
    render_chart,
    render_dasha,
    render_rahu_kaala,
    render_today,
    today_facts,
)
from ..store import Home, Store
from . import flow

log = logging.getLogger("samay")
STORE_KEY, ALLOWED_KEY = "store", "allowed"
FORGET_YES, FORGET_NO = "forget:yes", "forget:no"
QA_PREFIX = "qa:"  # qa:<sa|en>:<topic>
BRIEF_PREFIX = "brief:"  # brief:<hour> or brief:off
BRIEF_HOURS = (6, 7, 8, 9)
BRIEF_CHECK_SECONDS = 300
CHART_PREFIX = "img:"  # img:<south|north>:<0|1 = degrees shown>
NETWORK_TIMEOUT = 20.0  # seconds
MENU = ReplyKeyboardMarkup([list(row) for row in prompts.MENU_ROWS], resize_keyboard=True)


def _now() -> datetime:
    return datetime.now(UTC)


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
    if out.home is not None:
        await asyncio.to_thread(store.save_home, chat_id, *out.home)
        await asyncio.to_thread(store.delete_draft, chat_id)
        await _say(update, out.reply.text, MENU)
        place = geo.get_place(out.home[1])
        rahu = await asyncio.to_thread(service.rahu_kaala_for, place, _now())
        await _say(update, render_rahu_kaala(rahu, place.label), MENU)
        return
    if out.done is not None:
        await asyncio.to_thread(store.save_user, chat_id, out.done)
        await asyncio.to_thread(store.delete_draft, chat_id)
        await _say(update, out.reply.text, MENU)
        await _show(update, ctx, chat_id, "chart")
        return
    await _say(update, prefix + out.reply.text, _keyboard(out.reply))


async def _begin(update: Update, ctx, chat_id: int, prefix: str = "") -> None:
    await _send_flow(update, ctx, chat_id, flow.begin(), prefix)


async def _rahu_line(ctx, chat_id: int, now: datetime) -> str:
    """Today's Rahu Kaala for the city the person lives in, or a nudge to say where that is."""
    home = await asyncio.to_thread(_store(ctx).get_home, chat_id)
    if home is None:
        return f"{prompts.NEED_HOME} Tap “{prompts.MENU_HOME}”."
    place = geo.get_place(home.place_id)
    rahu = await asyncio.to_thread(service.rahu_kaala_for, place, now)
    return render_rahu_kaala(rahu, place.label)


async def _show(update: Update, ctx, chat_id: int, kind: str) -> None:
    saved = await asyncio.to_thread(_store(ctx).get_user, chat_id)
    if saved is None:
        await _begin(update, ctx, chat_id, prompts.NEED_BIRTH + "\n\n")
        return
    resolved = await asyncio.to_thread(service.resolve_birth, saved)
    if isinstance(resolved, NeedsDisambiguation):
        await _begin(update, ctx, chat_id, prompts.CHANGED + "\n\n")
        return
    now = _now()
    if kind == "today":
        report = await asyncio.to_thread(service.today_report, resolved, now)
        reading = await narrate.narrate(today_facts(report)) if narrate.enabled() else None
        extras = (await _rahu_line(ctx, chat_id, now),)
        text = render_today(report, reading, technical=False, extras=extras)
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


async def _resolved_birth(ctx, chat_id: int) -> ResolvedBirth | None:
    saved = await asyncio.to_thread(_store(ctx).get_user, chat_id)
    if saved is None:
        return None
    resolved = await asyncio.to_thread(service.resolve_birth, saved)
    return resolved if isinstance(resolved, ResolvedBirth) else None


def answer_markup(answer: qa.Answer, sanskrit: bool) -> InlineKeyboardMarkup | ReplyKeyboardMarkup:
    """A Sanskrit/English switch when an entry in the answer has a checked verse; else the menu."""
    if not any(e.shows_verse for e in answer.entries):
        return MENU
    label, mode = (prompts.BTN_ENGLISH, "en") if sanskrit else (prompts.BTN_SANSKRIT, "sa")
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"{QA_PREFIX}{mode}:{answer.topic}")]])


async def _answer_question(update: Update, ctx, chat_id: int, question: str) -> None:
    """Sort the question into a topic, answer from checked entries and chart facts, and count the
    topic (never the words) when there is no sourced answer."""
    topic = await qa.sort_with_model(question) if narrate.enabled() else qa.sort_question(question)
    birth = await _resolved_birth(ctx, chat_id)
    answer = await asyncio.to_thread(qa.answer_topic, topic, birth, _now(), None, question)
    if answer.topic is not None and not answer.entries:
        await asyncio.to_thread(_store(ctx).record_miss, answer.topic)
    await _say(update, render_answer(answer, birth_known=birth is not None), answer_markup(answer, False))


async def _toggle_answer(update: Update, ctx, chat_id: int, choice: str) -> None:
    mode, _, topic = choice.partition(":")
    if mode not in ("sa", "en") or topic not in qa.TOPICS:
        return
    birth = await _resolved_birth(ctx, chat_id)
    answer = await asyncio.to_thread(qa.answer_topic, topic, birth, _now())
    sanskrit = mode == "sa"
    try:
        await update.callback_query.edit_message_text(
            render_answer(answer, sanskrit, birth_known=birth is not None),
            reply_markup=answer_markup(answer, sanskrit),
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


@guarded
async def cmd_ask(update: Update, ctx) -> None:
    question = " ".join(ctx.args or ())
    if not question:
        await _say(update, prompts.ASK_QUESTION, MENU)
        return
    await _answer_question(update, ctx, update.effective_chat.id, question)


@guarded
async def cmd_home(update: Update, ctx) -> None:
    await _send_flow(update, ctx, update.effective_chat.id, flow.begin_home())


def _hour_label(hour: int) -> str:
    return f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}"


def brief_markup() -> InlineKeyboardMarkup:
    hours = [InlineKeyboardButton(_hour_label(h), callback_data=f"{BRIEF_PREFIX}{h}") for h in BRIEF_HOURS]
    off = [InlineKeyboardButton(prompts.BTN_BRIEF_OFF, callback_data=f"{BRIEF_PREFIX}off")]
    return InlineKeyboardMarkup([hours, off])


def _brief_status(home: Home, place) -> str:
    if home.brief_hour is None:
        return prompts.BRIEF_STATUS_OFF
    return prompts.BRIEF_STATUS_ON.format(time=_hour_label(home.brief_hour), place=place.name)


@guarded
async def cmd_brief(update: Update, ctx) -> None:
    chat_id = update.effective_chat.id
    home = await asyncio.to_thread(_store(ctx).get_home, chat_id)
    if home is None:
        await _send_flow(update, ctx, chat_id, flow.begin_home(), prompts.BRIEF_NEED_HOME)
        return
    place = geo.get_place(home.place_id)
    await _say(update, f"{_brief_status(home, place)}\n\n{prompts.BRIEF_ASK}", brief_markup())


async def _set_brief(update: Update, ctx, chat_id: int, choice: str) -> None:
    hours = {str(h): h for h in BRIEF_HOURS}
    if choice != "off" and choice not in hours:
        return
    store = _store(ctx)
    home = await asyncio.to_thread(store.get_home, chat_id)
    if home is None:
        await _send_flow(update, ctx, chat_id, flow.begin_home(), prompts.BRIEF_NEED_HOME)
        return
    hour = None if choice == "off" else hours[choice]
    await asyncio.to_thread(store.set_brief, chat_id, hour)
    place = geo.get_place(home.place_id)
    text = prompts.BRIEF_OFF if hour is None else prompts.BRIEF_ON.format(time=_hour_label(hour), place=place.name)
    await _say(update, text, MENU)


def compose_brief(saved: BirthInput | None, place, now: datetime) -> str:
    """The morning message for someone living at `place`. Synchronous; the bot runs it in a thread."""
    dasha = None
    if saved is not None:
        resolved = service.resolve_birth(saved)
        if isinstance(resolved, ResolvedBirth):
            dasha = service.today_report(resolved, now).current_dasha
    local_now = now.astimezone(ZoneInfo(place.tz))
    return render_brief(local_now, service.rahu_kaala_for(place, now), place.label, dasha)


async def _brief_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Every few minutes: send the morning message to anyone whose local hour has come and who has
    not had one today. Restart-safe, because "sent today" is stored."""
    store, allowed = ctx.application.bot_data[STORE_KEY], ctx.application.bot_data[ALLOWED_KEY]
    now = _now()
    for chat_id, home in await asyncio.to_thread(store.briefs_enabled):
        if chat_id not in allowed:
            continue
        try:
            place = geo.get_place(home.place_id)
            today = now.astimezone(ZoneInfo(place.tz))
            if today.hour != home.brief_hour or home.brief_last == today.date().isoformat():
                continue
            saved = await asyncio.to_thread(store.get_user, chat_id)
            text = await asyncio.to_thread(compose_brief, saved, place, now)
            await ctx.bot.send_message(chat_id, text, reply_markup=MENU)
            await asyncio.to_thread(store.mark_brief_sent, chat_id, today.date().isoformat())
        except Exception as e:  # noqa: BLE001 - one person's failure must not stop the others
            log.error("morning message failed chat=%s error=%s", chat_id, type(e).__name__)


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
        prompts.MENU_HOME: lambda: cmd_home(update, ctx),
        prompts.MENU_ASK: lambda: _say(update, prompts.ASK_QUESTION, MENU),
        prompts.MENU_BRIEF: lambda: cmd_brief(update, ctx),
        prompts.MENU_FORGET: lambda: cmd_forget(update, ctx),
    }
    if text in shortcuts:
        await shortcuts[text]()
        return
    stored = await asyncio.to_thread(store.get_draft, chat_id)
    if stored is None:
        await _answer_question(update, ctx, chat_id, text)
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
    if data.startswith(QA_PREFIX):
        await _toggle_answer(update, ctx, chat_id, data[len(QA_PREFIX):])
        return
    if data.startswith(BRIEF_PREFIX):
        await _set_brief(update, ctx, chat_id, data[len(BRIEF_PREFIX):])
        return
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
                     ("home", cmd_home), ("brief", cmd_brief), ("ask", cmd_ask),
                     ("chart", _command("chart")), ("dasha", _command("dasha")), ("today", _command("today"))]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    if app.job_queue is not None:
        app.job_queue.run_repeating(_brief_job, interval=BRIEF_CHECK_SECONDS, first=15, name="morning_brief")
    else:
        log.warning("job queue unavailable: morning messages are disabled")
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
    try:
        store = Store()
    except SamayError as e:  # a missing or wrong database key
        raise SystemExit(f"cannot open the database: {e}") from None
    app = build_application(token, allowed, store)
    log.info("samay starting (long polling, %d allowed chat(s))", len(allowed))
    # bootstrap_retries=-1: keep retrying the first connection instead of exiting if Telegram is
    # briefly unreachable.
    try:
        app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY], bootstrap_retries=-1)
    except InvalidToken:
        # The library's own message includes the token, so do not let it reach the logs.
        raise SystemExit("Telegram rejected the bot token: check TELEGRAM_TOKEN") from None
