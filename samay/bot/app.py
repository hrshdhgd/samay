"""Telegram adapter: allowlist, handlers, persisted drafts. All logic lives in flow/service/render.

Long polling, so no inbound port or TLS. Synchronous work runs in a worker thread. Logs carry
chat ids and error types only, never birth details.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import functools
import logging
import os
import time
from dataclasses import replace
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
from telegram.constants import ChatAction
from telegram.error import BadRequest, InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .. import narrate, narrative, qa, service
from ..engine import geo
from ..engine.errors import SamayError, TooManyPeople
from ..models import BirthInput, NeedsDisambiguation, ResolvedBirth
from ..render import prompts
from ..render.chart_image import STYLES, render_chart_png
from ..render.text import (
    render_ai,
    render_answer,
    render_brief,
    render_chart,
    render_dasha,
    render_rahu_kaala,
    render_today,
    today_facts,
)
from ..store import MAX_PEOPLE, Home, Person, Store
from ..subject import SELF, Subject
from . import flow

log = logging.getLogger("samay")
STORE_KEY, ALLOWED_KEY, LOCKS_KEY = "store", "allowed", "chat_locks"
FORGET_YES, FORGET_NO = "forget:yes", "forget:no"
QA_PREFIX = "qa:"  # qa:<sa|en|full>:<topic>
QA_VIEWS = {"sa": "sanskrit", "en": "compact", "full": "full"}
CHAT_KEY = "chats"  # in memory only: a few recent turns per chat, so follow-ups make sense
CHAT_TURNS = 4
SESSION_KEY = "sessions"  # in memory only: whom the chat is about, people not saved, who was just added
PEOPLE_PREFIX = "ppl:"  # ppl:<add|me|use:ID|del:ID|delyes:ID|delno:ID>
CHAT_TTL_SECONDS = 15 * 60
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


DEBOUNCE_SECONDS = 3.0
TYPING_REFRESH_SECONDS = 4.0  # Telegram shows "typing…" for about 5 seconds, so it is renewed until the work is done
RECENT_KEY = "recent"


def _monotonic() -> float:
    return time.monotonic()


def debounced(handler):
    """Answer a message once when the same text arrives again within DEBOUNCE_SECONDS in the same chat: a
    double tap, or a Telegram client that sent it twice. A handler that another handler calls for the same
    update (the menu buttons call the command handlers) still runs, because the update id is the same."""

    @functools.wraps(handler)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        message, chat = update.effective_message, update.effective_chat
        text = getattr(message, "text", None)
        if text and chat is not None:
            recent = ctx.application.bot_data.setdefault(RECENT_KEY, {})
            now, uid = _monotonic(), getattr(update, "update_id", id(update))
            for stale in [k for k, (t, _) in recent.items() if now - t > DEBOUNCE_SECONDS]:
                del recent[stale]
            seen = recent.get((chat.id, text))
            if seen is not None and seen[1] != uid:
                log.info("ignored a repeated message chat=%s", chat.id)
                return None
            recent.setdefault((chat.id, text), (now, uid))
        return await handler(update, ctx)

    return wrapper


@contextlib.asynccontextmanager
async def typing(update: Update, action: str = ChatAction.TYPING):
    """Show "typing…" (or another chat action) in the chat for as long as the block runs, so a slow answer does not
    look like a dead bot. Failing to send the indicator never stops the answer."""
    chat = update.effective_chat
    send = getattr(chat, "send_action", None)

    async def keep_showing() -> None:
        while True:
            try:
                await send(action)
            except Exception as e:  # noqa: BLE001 - a cosmetic hint must never break the reply
                log.debug("chat action not sent: %s", type(e).__name__)
            await asyncio.sleep(TYPING_REFRESH_SECONDS)

    task = asyncio.create_task(keep_showing()) if send is not None else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def chart_markup(style: str, degrees: bool) -> InlineKeyboardMarkup:
    """The two switches under the chart picture: South/North style and degrees on/off."""
    other = "north" if style == "south" else "south"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🔄 {other.title()} Indian", callback_data=f"{CHART_PREFIX}{other}:{int(degrees)}"),
        InlineKeyboardButton("🔢 Hide degrees" if degrees else "🔢 Show degrees",
                             callback_data=f"{CHART_PREFIX}{style}:{int(not degrees)}"),
    ]])


_LOCK_HELD: contextvars.ContextVar[frozenset] = contextvars.ContextVar("chat_lock_held", default=frozenset())


def guarded(handler):
    """Ignore, silently, anyone who is not on the allowlist."""

    @functools.wraps(handler)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat is None or chat.id not in ctx.application.bot_data[ALLOWED_KEY]:
            return None
        if update.callback_query is not None:  # a tap never waits behind a slow model call
            return await handler(update, ctx)
        # Updates run concurrently, but a chat's messages and commands still go one at a time, in order.
        if chat.id in _LOCK_HELD.get():  # a handler that calls another guarded handler already holds the lock
            return await handler(update, ctx)
        locks = ctx.application.bot_data.setdefault(LOCKS_KEY, {})
        async with locks.setdefault(chat.id, asyncio.Lock()):
            token = _LOCK_HELD.set(_LOCK_HELD.get() | {chat.id})
            try:
                return await handler(update, ctx)
            finally:
                _LOCK_HELD.reset(token)

    return wrapper


def _store(ctx) -> Store:
    return ctx.application.bot_data[STORE_KEY]


async def _say(update: Update, text: str, markup=None) -> None:
    message = update.effective_message
    await message.reply_text(text, reply_markup=markup)


async def _send_flow(update: Update, ctx, chat_id: int, out: flow.Outcome, prefix: str = "") -> None:
    store = _store(ctx)
    note = ""
    if out.person is not None:
        saved = await _record_person(ctx, chat_id, out.person)
        if out.person.save and not saved:
            note = "\n\n" + prompts.PEOPLE_FULL.format(limit=MAX_PEOPLE)
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
    if out.person is not None and out.draft is None:  # the last of the people just described is confirmed
        await asyncio.to_thread(store.delete_draft, chat_id)
        names = [name for _, name, kept in _session(ctx, chat_id)["intake"] if kept]
        saved_line = "\n" + prompts.PEOPLE_SAVED_LIST.format(names=", ".join(names)) if names else ""
        await _say(update, out.reply.text + saved_line + note, MENU)
        if out.then is not None:
            await _answer_intake(update, ctx, chat_id, *out.then)
        else:
            _session(ctx, chat_id)["intake"] = []
        return
    await _say(update, prefix + out.reply.text + note, _keyboard(out.reply))


async def _begin(update: Update, ctx, chat_id: int, prefix: str = "") -> None:
    await _send_flow(update, ctx, chat_id, flow.begin(), prefix)


async def _home_tz(ctx, chat_id: int) -> str | None:
    """The timezone of where the person lives now, for dates in a reading; None when they have not said."""
    home = await asyncio.to_thread(_store(ctx).get_home, chat_id)
    place = geo.get_place(home.place_id) if home is not None else None
    return place.tz if place is not None else None


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
        reading = await narrate.narrate(today_facts(report)) if narrate.rewording_enabled() else None
        extras = (await _rahu_line(ctx, chat_id, now),)
        text = render_today(report, reading, technical=False, extras=extras)
    else:
        natal = await asyncio.to_thread(service.natal_report, resolved)
        if kind == "chart":
            async with typing(update, ChatAction.UPLOAD_PHOTO):
                picture = await asyncio.to_thread(render_chart_png, natal, "south", False)
            await update.effective_message.reply_photo(photo=picture, reply_markup=chart_markup("south", False))
        text = render_dasha(natal, now, technical=False) if kind == "dasha" else render_chart(natal, technical=False)
    await _say(update, text, MENU)


@guarded
@debounced
async def cmd_start(update: Update, ctx) -> None:
    await _say(update, prompts.WELCOME, MENU)


@guarded
@debounced
async def cmd_help(update: Update, ctx) -> None:
    await _say(update, prompts.help_text(), MENU)


@guarded
@debounced
async def cmd_birth(update: Update, ctx) -> None:
    await _begin(update, ctx, update.effective_chat.id)


async def _resolved_birth(ctx, chat_id: int) -> ResolvedBirth | None:
    saved = await asyncio.to_thread(_store(ctx).get_user, chat_id)
    if saved is None:
        return None
    resolved = await asyncio.to_thread(service.resolve_birth, saved)
    return resolved if isinstance(resolved, ResolvedBirth) else None


def _session(ctx, chat_id: int) -> dict:
    """In-memory state for one chat: whom we are talking about (None is the user), people not saved, and who was just
    added. Never written to disk or logged; it expires with the conversation memory."""
    sessions = ctx.application.bot_data.setdefault(SESSION_KEY, {})
    now = _monotonic()
    state = sessions.get(chat_id)
    if state is None or now - state["touched"] > CHAT_TTL_SECONDS:
        state = sessions[chat_id] = {"active": None, "guests": {}, "intake": [], "next_guest": -1, "touched": now}
    state["touched"] = now
    return state


async def _people(ctx, chat_id: int) -> list[Person]:
    """Saved people first, then the ones added just for now (those have negative ids)."""
    saved = await asyncio.to_thread(_store(ctx).list_people, chat_id)
    return [*saved, *_session(ctx, chat_id)["guests"].values()]


async def _person_by_id(ctx, chat_id: int, pid: int) -> Person | None:
    if pid < 0:
        return _session(ctx, chat_id)["guests"].get(pid)
    return await asyncio.to_thread(_store(ctx).get_person, chat_id, pid)


async def _record_person(ctx, chat_id: int, result: flow.PersonResult) -> bool:
    """A confirmed person becomes the one we are talking about. They are saved (encrypted) if the user chose that,
    otherwise, or when there is no room left, kept in memory only. True if they were saved."""
    state = _session(ctx, chat_id)
    pid, saved = None, False
    if result.save:
        try:
            pid = await asyncio.to_thread(_store(ctx).save_person, chat_id, result.name, result.relation or None,
                                          result.birth)
            saved = True
        except TooManyPeople:
            pid = None
    if pid is None:
        for gid in [g for g, who in state["guests"].items() if who.name.casefold() == result.name.casefold()]:
            del state["guests"][gid]
        pid, state["next_guest"] = state["next_guest"], state["next_guest"] - 1
        state["guests"][pid] = Person(pid, result.name, result.relation or None, result.birth)
    state["active"] = pid
    state["intake"].append((pid, result.name, saved))
    return saved


async def _subject_and_birth(ctx, chat_id: int, pid: int | None) -> tuple[Subject, ResolvedBirth | None]:
    """Whom an answer is about and their resolved birth: the user (pid None), or a person. A person who has been
    deleted since sends us back to the user."""
    if pid is not None:
        person = await _person_by_id(ctx, chat_id, pid)
        if person is not None:
            resolved = await asyncio.to_thread(service.resolve_birth, person.birth)
            if not isinstance(resolved, ResolvedBirth):
                return Subject(person.name, person.relation or None), None
            minor = (_now() - resolved.utc).days < 18 * 365.25
            return Subject(person.name, person.relation or None, minor), resolved
        _session(ctx, chat_id)["active"] = None
    return SELF, await _resolved_birth(ctx, chat_id)


def _switch(state: dict, name: str | None, people: list[Person]) -> bool:
    """Make the router's choice of person the active one. True if the person changed."""
    if name is None:
        return False
    if name == "me":
        changed, state["active"] = state["active"] is not None, None
        return changed
    person = next((p for p in reversed(people) if p.name.casefold() == name.casefold()), None)
    if person is None or person.id == state["active"]:
        return False
    state["active"] = person.id
    return True


def answer_markup(
    answer: qa.Answer, view: str = "compact", pid: int | None = None
) -> InlineKeyboardMarkup | ReplyKeyboardMarkup:
    """Buttons under a sourced answer: more or less detail, and the Sanskrit view when a checked verse exists. With
    nothing to switch between, the normal menu. `pid` ties the buttons to the person the answer was about, so a tap
    later still shows that person's answer even if the conversation has moved on."""
    tag = "" if pid is None else f"@{pid}"
    if view == "sanskrit":
        row = [InlineKeyboardButton(prompts.BTN_ENGLISH, callback_data=f"{QA_PREFIX}en{tag}:{answer.topic}")]
    else:
        row = []
        if view == "full":
            row.append(InlineKeyboardButton(prompts.BTN_LESS, callback_data=f"{QA_PREFIX}en{tag}:{answer.topic}"))
        elif len(answer.entries) > 1 or answer.outlook is not None or answer.ashtaka is not None:
            row.append(InlineKeyboardButton(prompts.BTN_MORE, callback_data=f"{QA_PREFIX}full{tag}:{answer.topic}"))
        if any(e.shows_verse for e in answer.entries):
            row.append(InlineKeyboardButton(prompts.BTN_SANSKRIT, callback_data=f"{QA_PREFIX}sa{tag}:{answer.topic}"))
    return InlineKeyboardMarkup([row]) if row else MENU


def _recent_turns(ctx, chat_id: int) -> list[tuple[float, str | None, str, str]]:
    """(time, topic, question, reply) for this chat's last few turns, if recent. Never written to disk or logged."""
    now = _monotonic()
    turns = ctx.application.bot_data.get(CHAT_KEY, {}).get(chat_id, [])
    return [t for t in turns if now - t[0] <= CHAT_TTL_SECONDS]


def _remember_turn(ctx, chat_id: int, topic: str | None, question: str, reply: str) -> None:
    chats = ctx.application.bot_data.setdefault(CHAT_KEY, {})
    chats[chat_id] = [*_recent_turns(ctx, chat_id), (_monotonic(), topic, question[:200], reply[:400])][-CHAT_TURNS:]


async def _start_intake(update: Update, ctx, chat_id: int, text: str) -> None:
    """A message that describes people: the model reads it, then each person is checked and confirmed."""
    async with typing(update):
        extracted = await narrative.extract_people(text)
    _session(ctx, chat_id)["intake"] = []
    if extracted is None:  # the model could not read it: ask step by step instead
        await _send_flow(update, ctx, chat_id, flow.begin_person(narrate=False), prompts.NARRATE_FAILED + "\n\n")
        return
    await _send_flow(update, ctx, chat_id, flow.from_extraction(extracted))


async def _answer_intake(update: Update, ctx, chat_id: int, question: str, about: str) -> None:
    """The question that came with the details: answered for the person it names, or for each person just added."""
    state = _session(ctx, chat_id)
    added = [(pid, name) for pid, name, _ in state["intake"]]
    state["intake"] = []
    named = next((pid for pid, name in added if about and name.casefold() == about.casefold()), None)
    for pid in [named] if named is not None else [pid for pid, _ in added]:
        state["active"] = pid
        await _answer_question(update, ctx, chat_id, question, allow_intake=False)


async def _answer_question(update: Update, ctx, chat_id: int, question: str, allow_intake: bool = True) -> None:
    """Understand the message: whom it is about, and what is asked. Answer from checked entries and that person's chart
    facts and, when the local model is on, follow with its own labelled answer. A message that describes someone starts
    the intake instead. Only a topic key is counted when nothing sourced exists; the words are kept in memory for a few
    turns so follow-ups work, and nowhere else."""
    ai = narrate.enabled()
    state = _session(ctx, chat_id)
    people = await _people(ctx, chat_id)
    turns = _recent_turns(ctx, chat_id)
    history = [(q, r) for _, _, q, r in turns]
    current = next((p for p in people if p.id == state["active"]), None)
    if ai:
        async with typing(update):
            route = await qa.route_with_model(
                question, previous=turns[-1][1] if turns else None,
                people=[(p.name, p.relation) for p in people], active=current.name if current else None)
    else:
        named = narrative.match_person(question, people)
        route = replace(qa.rule_route(question), person=named.name if named else None)
    if route.add and allow_intake:
        await _start_intake(update, ctx, chat_id, question)
        return
    changed = _switch(state, route.person, people)
    pid = state["active"]
    subject, birth = await _subject_and_birth(ctx, chat_id, pid)
    pid = state["active"]  # a deleted person sends us back to the user
    if not subject.is_self and birth is None:
        await _say(update, prompts.PERSON_UNRESOLVED.format(name=subject.name), MENU)
        return
    if changed and subject.is_self:
        await _say(update, prompts.SWITCHED_SELF, MENU)
    tz = await _home_tz(ctx, chat_id)
    answer = await asyncio.to_thread(qa.answer_topic, route.topic, birth, _now(), None, question, subject, tz)
    if answer.topic is not None and not answer.topic.startswith(qa.COMPUTED_PREFIXES) and not answer.entries:
        await asyncio.to_thread(_store(ctx).record_miss, answer.topic)
    if ai and answer.topic is None:  # small talk, or nothing in the topics: just the model, labelled as such
        async with typing(update):
            reply = await qa.ai_answer(question, answer, history=history)
        if reply:
            _remember_turn(ctx, chat_id, None, question, reply)
            await _say(update, render_ai(reply), MENU)
        else:
            await _say(update, prompts.NO_TOPIC, MENU)
        return
    sourced = render_answer(answer, birth_known=birth is not None, ai_follows=ai)
    await _say(update, sourced, answer_markup(answer, pid=pid))
    if ai:
        # A second message, so the sourced answer is never delayed by the (slower) model.
        async with typing(update):
            reply = await qa.ai_answer(question, answer, history=history)
        if reply:
            _remember_turn(ctx, chat_id, answer.topic, question, reply)
        await _say(update, render_ai(reply) if reply else prompts.AI_UNAVAILABLE, MENU)


async def _toggle_answer(update: Update, ctx, chat_id: int, choice: str) -> None:
    head, _, topic = choice.partition(":")
    mode, _, pid_text = head.partition("@")
    if mode not in QA_VIEWS or topic not in qa.TOPICS:
        return
    pid = None
    if pid_text:
        try:
            pid = int(pid_text)
        except ValueError:
            return
        if await _person_by_id(ctx, chat_id, pid) is None:
            await _say(update, prompts.PERSON_GONE, MENU)
            return
    subject, birth = await _subject_and_birth(ctx, chat_id, pid)
    tz = await _home_tz(ctx, chat_id)
    answer = await asyncio.to_thread(qa.answer_topic, topic, birth, _now(), None, "", subject, tz)
    view = QA_VIEWS[mode]
    try:
        await update.callback_query.edit_message_text(
            render_answer(answer, view, birth_known=birth is not None), reply_markup=answer_markup(answer, view, pid)
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


@guarded
@debounced
async def cmd_ask(update: Update, ctx) -> None:
    question = " ".join(ctx.args or ())
    if not question:
        await _say(update, prompts.ASK_QUESTION, MENU)
        return
    await _answer_question(update, ctx, update.effective_chat.id, question)


def _people_markup(people: list[Person], active: int | None) -> InlineKeyboardMarkup:
    rows = []
    for p in people:
        label = ("✅ " if p.id == active else "") + p.name + (f" ({p.relation})" if p.relation else "")
        label += "" if p.id > 0 else " · not saved"
        rows.append([InlineKeyboardButton(label, callback_data=f"{PEOPLE_PREFIX}use:{p.id}"),
                     InlineKeyboardButton("🗑", callback_data=f"{PEOPLE_PREFIX}del:{p.id}")])
    rows.append([
        InlineKeyboardButton(("✅ " if active is None else "") + prompts.BTN_ABOUT_ME, callback_data=f"{PEOPLE_PREFIX}me"),
        InlineKeyboardButton(prompts.BTN_ADD_PERSON, callback_data=f"{PEOPLE_PREFIX}add"),
    ])
    return InlineKeyboardMarkup(rows)


@guarded
@debounced
async def cmd_people(update: Update, ctx) -> None:
    chat_id = update.effective_chat.id
    people = await _people(ctx, chat_id)
    head = prompts.PEOPLE_TITLE + ("" if people else "\n\n" + prompts.PEOPLE_EMPTY)
    await _say(update, head, _people_markup(people, _session(ctx, chat_id)["active"]))


async def _people_button(update: Update, ctx, chat_id: int, data: str) -> None:
    action, _, arg = data.partition(":")
    state = _session(ctx, chat_id)
    if action == "add":
        await _send_flow(update, ctx, chat_id, flow.begin_person(narrate.enabled()))
        return
    if action == "me":
        state["active"] = None
        await _say(update, prompts.SWITCHED_SELF, MENU)
        return
    try:
        pid = int(arg)
    except ValueError:
        return
    person = await _person_by_id(ctx, chat_id, pid)
    if action not in ("use", "del", "delyes", "delno"):
        return
    if person is None:
        await _say(update, prompts.PERSON_GONE, MENU)
        return
    if action == "use":
        state["active"] = pid
        await _say(update, prompts.SWITCHED.format(name=person.name), MENU)
    elif action == "del":
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(prompts.BTN_REALLY_DELETE.format(name=person.name), callback_data=f"{PEOPLE_PREFIX}delyes:{pid}"),
            InlineKeyboardButton(prompts.BTN_NO, callback_data=f"{PEOPLE_PREFIX}delno:{pid}"),
        ]])
        await _say(update, prompts.ASK_DELETE_PERSON.format(name=person.name), markup)
    elif action == "delyes":
        if pid < 0:
            state["guests"].pop(pid, None)
        else:
            await asyncio.to_thread(_store(ctx).delete_person, chat_id, pid)
        if state["active"] == pid:
            state["active"] = None
        await _say(update, prompts.PERSON_DELETED.format(name=person.name), MENU)
    else:
        await _say(update, prompts.KEPT, MENU)


@guarded
@debounced
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
@debounced
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
@debounced
async def cmd_forget(update: Update, ctx) -> None:
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(prompts.BTN_YES_DELETE, callback_data=FORGET_YES),
        InlineKeyboardButton(prompts.BTN_NO, callback_data=FORGET_NO),
    ]])
    await _say(update, prompts.FORGET_ASK, markup)


def _command(kind: str):
    @guarded
    @debounced
    async def handler(update: Update, ctx) -> None:
        await _show(update, ctx, update.effective_chat.id, kind)

    return handler


@guarded
@debounced
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
        prompts.MENU_PEOPLE: lambda: cmd_people(update, ctx),
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
    draft = flow.Draft.from_dict(stored)
    if draft.step == "narrate" and narrate.enabled():  # a story about someone: the model reads it
        async with typing(update):
            extracted = await narrative.extract_people(text)
        out = flow.from_extraction(extracted, draft.profile) if extracted else flow.narrative_failed(draft)
    else:
        out = await asyncio.to_thread(flow.on_text, draft, text)
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
    try:
        await query.answer()
    except BadRequest as e:
        # A tap that waited behind a slow model call is too old to acknowledge; the button still works.
        if "too old" not in str(e).lower():
            raise
    chat_id, data = update.effective_chat.id, query.data or ""
    if data.startswith(QA_PREFIX):
        await _toggle_answer(update, ctx, chat_id, data[len(QA_PREFIX):])
        return
    if data.startswith(PEOPLE_PREFIX):
        await _people_button(update, ctx, chat_id, data[len(PEOPLE_PREFIX):])
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
            ctx.application.bot_data.get(CHAT_KEY, {}).pop(chat_id, None)  # and what was remembered in memory
            ctx.application.bot_data.get(SESSION_KEY, {}).pop(chat_id, None)  # including people not saved
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
        .concurrent_updates(True)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data[STORE_KEY], app.bot_data[ALLOWED_KEY] = store, allowed
    for name, fn in [("start", cmd_start), ("help", cmd_help), ("birth", cmd_birth), ("forget", cmd_forget),
                     ("home", cmd_home), ("brief", cmd_brief), ("ask", cmd_ask), ("people", cmd_people),
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
