"""The guided conversations as a pure state machine: your own birth details, your living city, and details of
someone else (a child, a spouse, a parent), which may arrive as a narrative the model has already read.

No Telegram imports: a draft plus a text or a button tap goes in; the next draft, a reply and (when finished) the
result come out. Every button carries the draft's token, so a tap from an old message (after a restart, or a
double tap) is recognised and answered kindly. Drafts are plain data, so they survive a restart.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime

from ..engine import geo
from ..engine.errors import NonexistentTime, SamayError
from ..engine.profiles import DEFAULT_PROFILE
from ..models import BirthInput, NeedsDisambiguation
from ..narrative import Extraction
from ..render import prompts
from ..render.text import clock12, render_options
from ..service import parse_clock, parse_date, resolve_birth
from ..subject import MAX_NAME, MAX_RELATION, clean

START_OVER = "new"
RELATIONS = ("daughter", "son", "wife", "husband", "mother", "father", "friend")


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
    purpose: str = "birth"  # "birth" (the user), "home" (their living city) or "person" (someone else)
    # --- someone else ---
    name: str = ""
    relation: str = ""
    relation_asked: bool = False
    narrate: bool = False  # the model can read a narrative, so "start over" begins with that
    queue: tuple = ()  # the other people from the same message, still to be checked (plain dicts)
    question: str = ""  # what was asked alongside the details, answered once they are done
    about: str = ""  # whom that question is about, if the message said

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Draft:
        return cls(
            **{
                **data,
                "options": tuple(data.get("options", ())),
                "queue": tuple(data.get("queue", ())),
            }
        )


@dataclass(frozen=True)
class PersonResult:
    name: str
    relation: str
    birth: BirthInput
    save: bool  # the user chose "save" rather than "just for now"


@dataclass(frozen=True)
class Outcome:
    draft: Draft | None
    reply: Reply
    done: BirthInput | None = None
    home: tuple[str, str] | None = None  # (what was typed, place id) when the living city is set
    person: PersonResult | None = None  # someone's details are confirmed
    then: tuple[str, str] | None = None  # (question, about) to answer now that the details are in


def _start_over() -> tuple[Button, ...]:
    return (Button(prompts.BTN_START_OVER, START_OVER),)


def _reply(text: str, rows: tuple[tuple[Button, ...], ...] = ()) -> Reply:
    return Reply(text, (*rows, _start_over()))


def _next(draft: Draft, **changes) -> Draft:
    return replace(draft, token=secrets.token_hex(2), **changes)


def _tap(draft: Draft, action: str) -> str:
    return f"{draft.token}|{action}"


def _for_other(draft: Draft) -> bool:
    return draft.purpose == "person"


def _birth_of(draft: Draft) -> BirthInput:
    return BirthInput(
        draft.date_text,
        draft.time_text,
        draft.place_text,
        draft.place_choice,
        draft.fold,
        draft.profile,
        draft.approx_for,
    )


def _summary(draft: Draft) -> str:
    place = geo.get_place(draft.place_choice)
    near = f" (the nearest town to “{draft.approx_for}”)" if draft.approx_for else ""
    more = ""
    if draft.queue:
        names = ", ".join(q.get("name") or "the next person" for q in draft.queue)
        more = prompts.CONFIRM_MORE.format(names=names)
    return prompts.CONFIRM_PERSON.format(
        name=draft.name,
        rel=f" ({draft.relation})" if draft.relation else "",
        date=f"{datetime.strptime(draft.date_text, '%Y-%m-%d'):%d %b %Y}",
        time=clock12(datetime.strptime(draft.time_text, "%H:%M")),
        place=place.label + near,
        more=more,
    )


def _ask(draft: Draft) -> Reply:
    """The question for the draft's current step."""
    other, name = _for_other(draft), draft.name
    match draft.step:
        case "narrate":
            return _reply(
                prompts.ASK_NARRATE,
                ((Button(prompts.BTN_GUIDED, _tap(draft, "guided")),),),
            )
        case "name":
            return _reply(prompts.ASK_NAME)
        case "relation":
            labels = [Button(r.title(), _tap(draft, f"rel={r}")) for r in RELATIONS]
            rows = (
                tuple(labels[:3]),
                tuple(labels[3:6]),
                (labels[6], Button(prompts.BTN_REL_SKIP, _tap(draft, "rel=skip"))),
            )
            return _reply(prompts.ASK_RELATION, rows)
        case "date":
            return _reply(prompts.ASK_DATE_FOR.format(name=name) if other else prompts.ASK_DATE)
        case "time":
            return _reply(prompts.ASK_TIME_FOR.format(name=name) if other else prompts.ASK_TIME)
        case "ampm":
            return _reply(
                prompts.ASK_AMPM,
                (
                    (
                        Button(prompts.BTN_AM, _tap(draft, "am")),
                        Button(prompts.BTN_PM, _tap(draft, "pm")),
                    ),
                ),
            )
        case "place":
            return _reply(prompts.ASK_PLACE_FOR.format(name=name) if other else prompts.ASK_PLACE)
        case "home_place":
            return _reply(prompts.ASK_HOME)
        case "nearby":
            return _reply(prompts.ASK_NEARBY.format(place=draft.approx_for))
        case "pick_place":
            rows = tuple(
                (Button(geo.get_place(pid).label, _tap(draft, f"place={pid}")),) for pid in draft.options
            )
            return _reply(
                (prompts.PICK_PLACE_FOR.format(name=name) if other else prompts.PICK_PLACE),
                rows,
            )
        case "pick_fold":
            rows = tuple((Button(label, _tap(draft, f"fold={i}")),) for i, label in enumerate(draft.options))
            return _reply(prompts.PICK_FOLD, rows)
        case "person_confirm":
            return _reply(
                _summary(draft),
                (
                    (
                        Button(
                            prompts.BTN_SAVE_PERSON.format(name=name),
                            _tap(draft, "save"),
                        ),
                    ),
                    (Button(prompts.BTN_KEEP_PERSON, _tap(draft, "keep")),),
                    (Button(prompts.BTN_FIX, _tap(draft, "fix")),),
                ),
            )
    raise ValueError(f"unknown step {draft.step!r}")


def begin_home() -> Outcome:
    draft = _next(Draft(step="home_place", purpose="home"))
    return Outcome(draft, _ask(draft))


def _finish_home(draft: Draft, place_id: str) -> Outcome:
    place = geo.get_place(place_id)
    return Outcome(
        None,
        Reply(prompts.HOME_SAVED.format(place=place.label)),
        home=(draft.place_text, place_id),
    )


def begin(profile: str = DEFAULT_PROFILE) -> Outcome:
    draft = _next(Draft(profile=profile))
    return Outcome(draft, _ask(draft))


def begin_person(narrate: bool, profile: str = DEFAULT_PROFILE) -> Outcome:
    """Start collecting details of someone else: a narrative if the model can read one, otherwise step by step."""
    draft = _next(
        Draft(
            step="narrate" if narrate else "name",
            purpose="person",
            narrate=narrate,
            profile=profile,
        )
    )
    return Outcome(draft, _ask(draft))


def _draft_from(item, *, queue: tuple, question: str, about: str, profile: str, narrate: bool) -> Draft:
    d = asdict(item) if is_dataclass(item) else dict(item)
    ask = d.get("ask_ampm")
    return _next(
        Draft(
            purpose="person",
            name=d.get("name", ""),
            relation=d.get("relation", ""),
            relation_asked=True,
            date_text=d.get("date_text", ""),
            time_text=d.get("time_text", ""),
            hour=ask[0] if ask else None,
            minute=ask[1] if ask else None,
            place_text=d.get("place_text", ""),
            queue=queue,
            question=question,
            about=about,
            profile=profile,
            narrate=narrate,
        )
    )


def from_extraction(ext: Extraction, profile: str = DEFAULT_PROFILE) -> Outcome:
    """The details the model read from a narrative: check the first person (asking only for what is missing); the
    others wait in the queue."""
    # Plain JSON-safe data (a list, not a tuple, for the pair), so a draft equals itself after a restart.
    queue = tuple({**asdict(p), "ask_ampm": list(p.ask_ampm) if p.ask_ampm else None} for p in ext.people[1:])
    draft = _draft_from(
        ext.people[0],
        queue=queue,
        question=ext.question,
        about=ext.about,
        profile=profile,
        narrate=True,
    )
    return _advance(draft)


def _go(draft: Draft, prefix: str = "", **changes) -> Outcome:
    draft = _next(draft, **changes)
    reply = _ask(draft)
    return Outcome(draft, replace(reply, text=prefix + reply.text) if prefix else reply)


def _advance(draft: Draft) -> Outcome:
    """Go to the first thing still missing, or finish. Fields already known (typed, or read from a narrative)
    are never asked again."""
    other = _for_other(draft)
    if other and not draft.name:
        return _go(draft, step="name")
    if other and not draft.relation and not draft.relation_asked:
        return _go(draft, step="relation")
    if not draft.date_text:
        return _go(draft, step="date")
    if draft.hour is not None:
        return _go(draft, step="ampm")
    if not draft.time_text:
        return _go(draft, step="time")
    if draft.place_choice:
        return _finish(draft)
    if draft.place_text:
        return _search(replace(draft, step="place"), draft.place_text)
    return _go(draft, step="place")


def _finish(draft: Draft) -> Outcome:
    """All details collected: check the local time against the place's clocks."""
    birth = _birth_of(draft)
    try:
        result = resolve_birth(birth)
    except NonexistentTime:
        return _go(draft, prompts.NONEXISTENT + "\n\n", step="time", hour=None, minute=None)
    except SamayError as e:
        return _go(draft, f"{e}\n\n", step="date", date_text="")
    if isinstance(result, NeedsDisambiguation):
        # A place is already chosen, so this can only be a repeated local time.
        labels = tuple(render_options(result))
        return _go(draft, step="pick_fold", options=labels)
    if _for_other(draft):
        return _go(draft, step="person_confirm")
    return Outcome(None, Reply(prompts.SAVED), birth)


def _person_done(draft: Draft, save: bool) -> Outcome:
    result = PersonResult(draft.name, draft.relation, _birth_of(draft), save)
    if draft.queue:
        following = _draft_from(
            draft.queue[0],
            queue=draft.queue[1:],
            question=draft.question,
            about=draft.about,
            profile=draft.profile,
            narrate=draft.narrate,
        )
        out = _advance(following)
        text = prompts.PERSON_NEXT.format(name=draft.name) + "\n\n" + out.reply.text
        return replace(out, reply=replace(out.reply, text=text), person=result)
    then = (draft.question, draft.about) if draft.question else None
    return Outcome(
        None,
        Reply(prompts.PERSON_DONE.format(name=draft.name)),
        person=result,
        then=then,
    )


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
        case "narrate":  # the model could not read it (or is off): fall back to asking step by step
            return narrative_failed(draft)
        case "name":
            name = clean(text, MAX_NAME)
            if not name:
                return Outcome(draft, _ask(draft))
            return _advance(replace(draft, name=name))
        case "relation":
            return _advance(
                replace(
                    draft,
                    relation=clean(text, MAX_RELATION).lower(),
                    relation_asked=True,
                )
            )
        case "date":
            try:
                day = parse_date(text)
            except SamayError:
                return Outcome(draft, _reply(prompts.BAD_DATE))
            return _advance(replace(draft, date_text=day.strftime("%Y-%m-%d")))
        case "time":
            try:
                clock = parse_clock(text)
            except SamayError:
                return Outcome(draft, _reply(prompts.BAD_TIME))
            if clock.ambiguous:
                return _advance(replace(draft, hour=clock.hour, minute=clock.minute))
            return _advance(
                replace(
                    draft,
                    time_text=f"{clock.hour:02d}:{clock.minute:02d}",
                    hour=None,
                    minute=None,
                )
            )
        case "home_place":
            return _search_home(draft, text)
        case "place" | "nearby":
            return _search(draft, text)
    return Outcome(draft, replace(_ask(draft), text=prompts.RE_ASK + "\n\n" + _ask(draft).text))


def narrative_failed(draft: Draft) -> Outcome:
    """The model could not read the narrative: say so and carry on step by step."""
    return _go(draft, prompts.NARRATE_FAILED + "\n\n", step="name", narrate=False)


def _stale() -> Outcome:
    return Reply(prompts.STALE, ((Button(prompts.BTN_START, START_OVER),),))


def on_button(draft: Draft | None, data: str) -> Outcome:
    if data == START_OVER:
        if draft is not None and draft.purpose == "person":
            return begin_person(draft.narrate, draft.profile)
        if draft is not None and draft.purpose == "home":
            return begin_home()
        return begin(draft.profile if draft else DEFAULT_PROFILE)
    token, _, action = data.partition("|")
    if draft is None or draft.token != token:
        return Outcome(draft, _stale())
    match draft.step, action.partition("="):
        case "ampm", ("am" | "pm", _, _):
            hour = draft.hour % 12 + (12 if action == "pm" else 0)
            return _advance(
                replace(
                    draft,
                    time_text=f"{hour:02d}:{draft.minute:02d}",
                    hour=None,
                    minute=None,
                )
            )
        case "pick_place", ("place", "=", pid) if pid in draft.options:
            if draft.purpose == "home":
                return _finish_home(draft, pid)
            return _finish(replace(draft, place_choice=pid))
        case "pick_fold", ("fold", "=", i) if i in ("0", "1"):
            return _finish(replace(draft, fold=int(i)))
        case "narrate", ("guided", _, _):
            return _advance(replace(draft, narrate=False))
        case "relation", ("rel", "=", value) if value in RELATIONS or value == "skip":
            return _advance(
                replace(
                    draft,
                    relation="" if value == "skip" else value,
                    relation_asked=True,
                )
            )
        case "person_confirm", ("save" | "keep", _, _):
            return _person_done(draft, save=action == "save")
        case "person_confirm", (
            "fix",
            _,
            _,
        ):  # keep who they are, ask for the rest again
            return _go(
                draft,
                step="date",
                date_text="",
                time_text="",
                hour=None,
                minute=None,
                place_text="",
                place_choice=None,
                approx_for=None,
                fold=None,
                options=(),
            )
    return Outcome(draft, _stale())
