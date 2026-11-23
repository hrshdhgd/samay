"""Plain words for the day's panchang, observance days and the morning message. Facts only: no outcome is promised."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..engine.panchang import tithi_name
from ..models import (
    NextObservanceReport,
    ObservanceDay,
    ObservanceListReport,
    PanchangReport,
)

NOTE_LOCAL = "A local panchang may differ, because traditions count this day differently."
CARE_PREFIX = "Traditional guidance (muhurta tradition; we have not checked the original text): "
NO_CLAIM = "Observance days are not named yet: the rules for them are not set up from a checked source."
NEED_TRADITION = (
    "To name observance days I need to know which tradition your family follows. Please set it first."
)
TOO_FAR = "I can only work out days between 1972 and 2150."
NO_SUN = "The Sun does not both rise and set that day in {place}, so I cannot give sunrise-based times."
WHICH_DATE = "I could not read that date. Which day do you mean? For example: 4 December 2026, or 2026-12-04."
NEED_PLACE = (
    "To work out the panchang I need to know where you live now, because the day starts at local sunrise."
)
WORKING = "Working that out, one moment."
TOO_LONG = "That range is too long: I can list at most 366 days at a time. Please ask for a year or less."
NOTE_LIST = (
    "Where a second day is shown, a local panchang may keep that day instead, because traditions count it "
    "differently."
)
LIST_SCOPE = (
    "These are the days the tithi rules name for each observance; whether and how to keep them is your "
    "family's custom."
)
GROUP_BY_MONTH_DAYS = 35  # a list longer than this gets a heading for each month

# How the Tulu month's first day is chosen, in one clause per profile choice (data/profiles/tulu.yaml).
CUTOFF_WORDS = {
    "same_day": "a month starts on the day the Sun moves into a new sign",
    "sunset": "a month starts on the day the Sun moves into a new sign if it does so before sunset, otherwise the next day",
    "aparahna": "a month starts on the day the Sun moves into a new sign if it does so by mid-afternoon, otherwise the "
    "next day",
    "next_day": "a month starts on the day after the Sun moves into a new sign",
}


def _day(d: date) -> str:
    return f"{d:%A, %d %B %Y}"


def _clock(moment: datetime, tz: str, day: date | None = None) -> str:
    """HH:MM in the place's own time; the date is added when it falls on a day other than `day`."""
    local = moment.astimezone(ZoneInfo(tz))
    return f"{local:%H:%M}" if day is None or local.date() == day else f"{local:%H:%M} on {local:%d %b}"


def _until(element, tz: str, day: date) -> str:
    return f"until {_clock(element.end, tz, day)}"


def _then(tithi, tz: str, day: date) -> str:
    """ ", then <next tithi> from HH:MM" when the next tithi begins later on the same local day, else nothing. It
    explains a day such as Dashami at sunrise but Ekadashi by the afternoon."""
    end = tithi.end.astimezone(ZoneInfo(tz))
    if end.date() != day:
        return ""
    return f", then {tithi_name(tithi.number % 30 + 1)} from {end:%H:%M}"


def _observance_lines(o: ObservanceDay, day: date | None = None) -> list[str]:
    """`day` is the day being described (None for "when is the next one"): on it the observance is kept by this
    calendar, by some calendars only, or not at all."""
    if o.primary is None:
        if o.explanation:  # a nakshatra note: shown as it is, with no date wording
            return [o.explanation]
        return [f"{o.label}: the rule I use gives no clear day for this one. {NOTE_LOCAL}"]
    others = [d for d, _ in o.alternates if d != day]
    if day is not None and day != o.primary and day in {d for d, _ in o.alternates}:
        tense = "was" if o.primary < day else "is"
        lines = [
            f"{o.label}: some calendars keep it today. The day I use {tense} {_day(o.primary)}. {NOTE_LOCAL}"
        ]
        if others:
            lines.append(f"Other calendars place it on {', '.join(_day(d) for d in others)}.")
    else:
        lines = [f"{o.label}: {'today' if o.primary == day else _day(o.primary)}."]
        if others:
            lines.append(f"Some calendars place it on {', '.join(_day(d) for d in others)}. {NOTE_LOCAL}")
    if o.explanation:
        lines.append(o.explanation)
    return lines


def _care_lines(report: PanchangReport) -> list[str]:
    return [f"{CARE_PREFIX}{text}" for text in report.care_notes]


def render_day(report: PanchangReport, day: date) -> str:
    f, tz, tulu = report.facts, report.tz, report.tulu
    rule = f"by the {report.cutoff.replace('_', ' ')} rule"
    if report.cutoff in CUTOFF_WORDS:
        rule += f": {CUTOFF_WORDS[report.cutoff]}"
    lines = [
        f"{_day(day)} in {report.place_label}",
        f"Tithi (the Moon's lunar day): {f.tithi.name}, {_until(f.tithi, tz, day)}{_then(f.tithi, tz, day)}.",
        f"Nakshatra (the Moon's star): {f.nakshatra.name}, {_until(f.nakshatra, tz, day)}.",
        f"Karana (half of the lunar day): {f.karana.name}. Yoga (the Sun and Moon taken together): {f.yoga.name}.",
        f"Sunrise {_clock(f.sunrise, tz)}, sunset {_clock(f.sunset, tz)}.",
        f"Tulu date: {tulu.month} {tulu.day} (the month began {tulu.month_starts:%d %b}; {rule}).",
    ]
    for o in report.observances:
        lines += _observance_lines(o, day)
    lines += _care_lines(report)
    if report.needs_sampradaya:
        lines.append(NEED_TRADITION)
    elif report.claims_withheld and all(o.primary is None for o in report.observances):
        lines.append(NO_CLAIM)
    return "\n".join(lines)


def render_next(report: NextObservanceReport) -> str:
    if report.needs_sampradaya:
        return NEED_TRADITION
    if not report.claim_available:
        return f"The day for {report.label} is not set up from a checked source yet, so I will not name one."
    if report.found is None or report.found.primary is None:
        return f"I could not find the next {report.label} in the coming weeks."
    return "\n".join(
        [f"The next {report.label} is {_day(report.found.primary)} in {report.place_label}."]
        + _observance_lines(report.found)[1:]
    )


def render_about(label: str, explanations: list[str], care_notes: tuple[str, ...] = ()) -> str:
    care = [f"{CARE_PREFIX}{text}" for text in care_notes]
    if not explanations:
        return "\n\n".join(
            [f"I have no checked source for {label} yet, so I will not describe what it means.", *care]
        )
    return "\n\n".join([*explanations, *care])


def render_avoid_window(rahu, place_label: str) -> str:
    """Rahu Kaala as the custom it is: a window traditionally avoided for new starts, not a forecast."""
    if rahu is None:
        return (
            f"The Sun does not both rise and set today in {place_label}, so there is no usual avoid-window."
        )
    return (
        f"Traditionally avoided for starting new things: {rahu.start:%H:%M} to {rahu.end:%H:%M} "
        f"(called Rahu Kaala), {place_label}."
    )


def render_brief(local_now: datetime, rahu, place_label: str, report: PanchangReport | None) -> str:
    """The morning message: date, the avoid-window, the Moon's day and star, any observance, the Tulu date."""
    today = local_now.date()
    lines = [
        f"🌅 Good morning! Today is {_day(today)}.",
        render_avoid_window(rahu, place_label),
    ]
    if report is not None:
        f, tz = report.facts, report.tz
        # Sent between 6 and 9 am, possibly after an element has ended, so it is anchored to sunrise, as a panchang is.
        lines.append(
            f"At sunrise: the Moon's lunar day (tithi) {f.tithi.name}, {_until(f.tithi, tz, today)}; "
            f"the Moon's star (nakshatra) {f.nakshatra.name}, {_until(f.nakshatra, tz, today)}."
        )
        for o in report.observances:
            lines += _observance_lines(o, today)
        lines += _care_lines(report)
        lines.append(f"Tulu date: {report.tulu.month} {report.tulu.day}.")
    return "\n".join(lines)


def _short(d: date, year: bool = False) -> str:
    return f"{d:%a} {d.day} {d:%b}" + (f" {d.year}" if year else "")


def _span(first: date, last: date, joiner: str) -> str:
    """ "Mon 23 Nov <joiner> Sun 29 Nov 2026", with the year on both ends only when they differ."""
    both = first.year != last.year
    return f"{_short(first, both)} {joiner} {_short(last, True)}"


def _and(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def render_list(report: ObservanceListReport) -> str:
    """One line per date ("Fri 27 Nov: Pradosha"), a second day some calendars keep in brackets, a heading for each
    month over a long range, and counts at the end. Names days only; never calls one good, lucky or auspicious.
    """
    if report.too_long:
        return TOO_LONG
    first, last = report.first, report.last
    inside = lambda d: d is not None and first <= d <= last
    by_date: dict[date, list[str]] = {}
    counted: dict[str, int] = {}
    unclear: list[str] = []
    for o in report.days:
        others = [d for d, _ in o.alternates if d != o.primary]
        if inside(o.primary):
            extra = f" (some calendars: {', '.join(_short(d) for d in others)})" if others else ""
            by_date.setdefault(o.primary, []).append(o.label + extra)
            counted[o.label] = counted.get(o.label, 0) + 1
            continue
        shown = [d for d in others if inside(d)]
        for d in shown:
            used = (
                ""
                if o.primary is None
                else f" (the day I use is {_short(o.primary, o.primary.year != d.year)})"
            )
            by_date.setdefault(d, []).append(f"{o.label} in some calendars{used}")
        if not shown and o.primary is None:
            unclear.append(o.label)
    what = _and(report.labels) if report.filtered else "observance"
    tail = []
    if report.withheld:
        tail.append(
            f"Not named: {_and(report.withheld)}, because the rules for "
            f"{'it are' if len(report.withheld) == 1 else 'them are'} not set up from a checked source yet."
        )
    if report.needs_sampradaya:
        tail.append(NEED_TRADITION)
    for label in dict.fromkeys(unclear):
        tail.append(f"{label}: the rule I use gives no clear day for one of these. {NOTE_LOCAL}")
    if not by_date:
        return "\n".join(
            [
                f"No {what} days fall between {_span(first, last, 'and')} in {report.place_label}.",
                *tail,
            ]
        )
    header = f"{what[0].upper()}{what[1:]} days from {_span(first, last, 'to')} in {report.place_label}"
    grouped = (last - first).days + 1 > GROUP_BY_MONTH_DAYS
    blocks, month = [header], None
    for d in sorted(by_date):
        line = f"{_short(d)}: {' and '.join(by_date[d])}"
        if grouped and (d.year, d.month) != month:
            month = (d.year, d.month)
            blocks.append(f"{d:%B %Y}\n{line}")
        else:
            blocks[-1] += f"\n{line}"
    tail.append(LIST_SCOPE)
    if any("some calendars" in "".join(entries) for entries in by_date.values()):
        tail.append(NOTE_LIST)
    if counted:
        order = list(report.labels) + sorted(set(counted) - set(report.labels))
        dates = sum(1 for d in by_date if any("in some calendars" not in e for e in by_date[d]))
        parts = ", ".join(f"{counted[label]} {label}" for label in order if label in counted)
        tail.append(f"{dates} {'day' if dates == 1 else 'days'}: {parts}.")
    return "\n\n".join(blocks) + "\n\n" + "\n".join(tail)
