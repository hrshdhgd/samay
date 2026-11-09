"""The guided birth-details conversation as a pure state machine.

No Telegram imports: a draft plus a text or a button tap goes in; the next draft, a reply and
(when finished) the completed BirthInput come out. Every button carries the draft's token, so a
tap from an old message (after a restart, or a double tap) is recognised and answered kindly.
"""
from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, replace

from ..engine import geo
from ..engine.errors import NonexistentTime, SamayError
from ..engine.profiles import DEFAULT_PROFILE
from ..models import BirthInput, NeedsDisambiguation
from ..render import prompts
from ..render.text import render_options
from ..service import parse_clock, parse_date, resolve_birth

START_OVER = "new"


@dataclass(frozen=True)
class Button:
    label: str
    data: str


@dataclass(frozen=True)
class Reply:
    text: str
    buttons: tuple[tuple[Button, ...], ...] = ()


@dataclass(frozen=True)
class Draft:
    step: str = "date"
    token: str = ""
    date_text: str = ""
    time_text: str = ""
    hour: int | None = None  # time typed without am/pm, waiting for the morning/evening answer
    minute: int | None = None
    place_text: str = ""
    approx_for: str | None = None
    place_choice: str | None = None
    fold: int | None = None
    options: tuple[str, ...] = ()
    profile: str = DEFAULT_PROFILE
    purpose: str = "birth"  # "birth", or "home" for the living-city question

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Draft:
        return cls(**{**data, "options": tuple(data.get("options", ()))})


@dataclass(frozen=True)
class Outcome:
    draft: Draft | None
    reply: Reply
    done: BirthInput | None = None
    home: tuple[str, str] | None = None  # (what was typed, place id) when the living city is set


def _start_over() -> tuple[Button, ...]:
    return (Button(prompts.BTN_START_OVER, START_OVER),)


def _reply(text: str, rows: tuple[tuple[Button, ...], ...] = ()) -> Reply:
    return Reply(text, (*rows, _start_over()))


def _next(draft: Draft, **changes) -> Draft:
    return replace(draft, token=secrets.token_hex(2), **changes)


def _tap(draft: Draft, action: str) -> str:
    return f"{draft.token}|{action}"


def _ask(draft: Draft) -> Reply:
    """The question for the draft's current step."""
    match draft.step:
        case "date":
            return _reply(prompts.ASK_DATE)
        case "time":
            return _reply(prompts.ASK_TIME)
        case "ampm":
            return _reply(prompts.ASK_AMPM, (
                (Button(prompts.BTN_AM, _tap(draft, "am")), Button(prompts.BTN_PM, _tap(draft, "pm"))),
            ))
        case "place":
            return _reply(prompts.ASK_PLACE)
        case "home_place":
            return _reply(prompts.ASK_HOME)
        case "nearby":
            return _reply(prompts.ASK_NEARBY.format(place=draft.approx_for))
        case "pick_place":
            rows = tuple(
                (Button(geo.get_place(pid).label, _tap(draft, f"place={pid}")),) for pid in draft.options
            )
            return _reply(prompts.PICK_PLACE, rows)
        case "pick_fold":
            rows = tuple(
                (Button(label, _tap(draft, f"fold={i}")),) for i, label in enumerate(draft.options)
            )
            return _reply(prompts.PICK_FOLD, rows)
    raise ValueError(f"unknown step {draft.step!r}")


def begin_home() -> Outcome:
    draft = _next(Draft(step="home_place", purpose="home"))
    return Outcome(draft, _ask(draft))


def _finish_home(draft: Draft, place_id: str) -> Outcome:
    place = geo.get_place(place_id)
    return Outcome(None, Reply(prompts.HOME_SAVED.format(place=place.label)), home=(draft.place_text, place_id))


def begin(profile: str = DEFAULT_PROFILE) -> Outcome:
    draft = _next(Draft(profile=profile))
    return Outcome(draft, _ask(draft))


def _go(draft: Draft, prefix: str = "", **changes) -> Outcome:
    draft = _next(draft, **changes)
    reply = _ask(draft)
    return Outcome(draft, replace(reply, text=prefix + reply.text) if prefix else reply)


def _finish(draft: Draft) -> Outcome:
    """All details collected: check the local time against the place's clocks."""
    birth = BirthInput(draft.date_text, draft.time_text, draft.place_text, draft.place_choice,
                       draft.fold, draft.profile, draft.approx_for)
    try:
        result = resolve_birth(birth)
    except NonexistentTime:
        return _go(draft, prompts.NONEXISTENT + "\n\n", step="time", hour=None, minute=None)
    except SamayError as e:
        return _go(draft, f"{e}\n\n", step="date")
    if isinstance(result, NeedsDisambiguation):
        # A place is already chosen, so this can only be a repeated local time.
        labels = tuple(render_options(result))
        return _go(draft, step="pick_fold", options=labels)
    return Outcome(None, Reply(prompts.SAVED), birth)


def _search_home(draft: Draft, text: str) -> Outcome:
    places = geo.find_places(text)
    if not places:
        return _go(draft, prompts.HOME_NOT_FOUND + "\n\n", step="home_place")
    draft = replace(draft, place_text=text)
    if len(places) == 1:
        return _finish_home(draft, places[0].id)
    return _go(draft, step="pick_place", options=tuple(p.id for p in places))


def _search(draft: Draft, text: str) -> Outcome:
    places = geo.find_places(text)
    first_try = draft.step == "place"
    if not places:
        if first_try:
            return _go(draft, step="nearby", approx_for=text, place_text="")
        return _go(draft, prompts.ASK_NEARBY_AGAIN + "\n\n", step="nearby")
    draft = replace(draft, place_text=text)
    if len(places) == 1:
        return _finish(replace(draft, place_choice=places[0].id))
    return _go(draft, step="pick_place", options=tuple(p.id for p in places))


def on_text(draft: Draft | None, text: str) -> Outcome:
    if draft is None:
        return begin()
    text = text.strip()
    match draft.step:
        case "date":
            try:
                day = parse_date(text)
            except SamayError:
                return Outcome(draft, _reply(prompts.BAD_DATE))
            return _go(draft, step="time", date_text=day.strftime("%Y-%m-%d"))
        case "time":
            try:
                clock = parse_clock(text)
            except SamayError:
                return Outcome(draft, _reply(prompts.BAD_TIME))
            if clock.ambiguous:
                return _go(draft, step="ampm", hour=clock.hour, minute=clock.minute)
            return _go(draft, step="place", time_text=f"{clock.hour:02d}:{clock.minute:02d}")
        case "home_place":
            return _search_home(draft, text)
        case "place" | "nearby":
            return _search(draft, text)
    return Outcome(draft, replace(_ask(draft), text=prompts.RE_ASK + "\n\n" + _ask(draft).text))


def on_button(draft: Draft | None, data: str) -> Outcome:
    if data == START_OVER:
        return begin(draft.profile if draft else DEFAULT_PROFILE)
    token, _, action = data.partition("|")
    if draft is None or draft.token != token:
        return Outcome(draft, Reply(prompts.STALE, ((Button(prompts.BTN_START, START_OVER),),)))
    match draft.step, action.partition("="):
        case "ampm", ("am" | "pm", _, _):
            hour = draft.hour % 12 + (12 if action == "pm" else 0)
            return _go(draft, step="place", time_text=f"{hour:02d}:{draft.minute:02d}", hour=None, minute=None)
        case "pick_place", ("place", "=", pid) if pid in draft.options:
            if draft.purpose == "home":
                return _finish_home(draft, pid)
            return _finish(replace(draft, place_choice=pid))
        case "pick_fold", ("fold", "=", i) if i in ("0", "1"):
            return _finish(replace(draft, fold=int(i)))
    return Outcome(draft, Reply(prompts.STALE, ((Button(prompts.BTN_START, START_OVER),),)))
