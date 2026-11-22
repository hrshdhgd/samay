"""Plain words for the day's panchang, observance days and the morning message. Facts only: no outcome is promised."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..models import NextObservanceReport, ObservanceDay, PanchangReport

NOTE_LOCAL = "A local panchang may differ, because traditions count this day differently."
NO_CLAIM = "Observance days are not named yet: the rules for them are not set up from a checked source."
NEED_TRADITION = "To name observance days I need to know which tradition your family follows. Please set it first."
TOO_FAR = "I can only work out days between 1972 and 2150."
NO_SUN = "The Sun does not both rise and set that day in {place}, so I cannot give sunrise-based times."

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


def _observance_lines(o: ObservanceDay, day: date | None = None) -> list[str]:
    """`day` is the day being described (None for "when is the next one"): on it the observance is kept by this
    calendar, by some calendars only, or not at all."""
    if o.primary is None:
        return [f"{o.label}: the rule I use gives no clear day for this one. {NOTE_LOCAL}"]
    others = [d for d, _ in o.alternates if d != day]
    if day is not None and day != o.primary and day in {d for d, _ in o.alternates}:
        tense = "was" if o.primary < day else "is"
        lines = [f"{o.label}: some calendars keep it today. The day I use {tense} {_day(o.primary)}. {NOTE_LOCAL}"]
        if others:
            lines.append(f"Other calendars place it on {', '.join(_day(d) for d in others)}.")
    else:
        lines = [f"{o.label}: {'today' if o.primary == day else _day(o.primary)}."]
        if others:
            lines.append(f"Some calendars place it on {', '.join(_day(d) for d in others)}. {NOTE_LOCAL}")
    if o.explanation:
        lines.append(o.explanation)
    return lines


def render_day(report: PanchangReport, day: date) -> str:
    f, tz, tulu = report.facts, report.tz, report.tulu
    rule = f"by the {report.cutoff.replace('_', ' ')} rule"
    if report.cutoff in CUTOFF_WORDS:
        rule += f": {CUTOFF_WORDS[report.cutoff]}"
    lines = [f"{_day(day)} in {report.place_label}",
             f"Tithi (the Moon's lunar day): {f.tithi.name}, {_until(f.tithi, tz, day)}.",
             f"Nakshatra (the Moon's star): {f.nakshatra.name}, {_until(f.nakshatra, tz, day)}.",
             f"Karana (half of the lunar day): {f.karana.name}. Yoga (the Sun and Moon taken together): {f.yoga.name}.",
             f"Sunrise {_clock(f.sunrise, tz)}, sunset {_clock(f.sunset, tz)}.",
             f"Tulu date: {tulu.month} {tulu.day} (the month began {tulu.month_starts:%d %b}; {rule})."]
    for o in report.observances:
        lines += _observance_lines(o, day)
    if report.needs_sampradaya:
        lines.append(NEED_TRADITION)
    elif report.claims_withheld and not report.observances:
        lines.append(NO_CLAIM)
    return "\n".join(lines)


def render_next(report: NextObservanceReport) -> str:
    if report.needs_sampradaya:
        return NEED_TRADITION
    if not report.claim_available:
        return f"The day for {report.label} is not set up from a checked source yet, so I will not name one."
    if report.found is None or report.found.primary is None:
        return f"I could not find the next {report.label} in the coming weeks."
    return "\n".join([f"The next {report.label} is {_day(report.found.primary)} in {report.place_label}."]
                     + _observance_lines(report.found)[1:])


def render_about(label: str, explanations: list[str]) -> str:
    if not explanations:
        return (f"I have no checked source for {label} yet, so I will not describe what it means. "
                "I can still tell you which day it falls on.")
    return "\n\n".join(explanations)


def render_avoid_window(rahu, place_label: str) -> str:
    """Rahu Kaala as the custom it is: a window traditionally avoided for new starts, not a forecast."""
    if rahu is None:
        return f"The Sun does not both rise and set today in {place_label}, so there is no usual avoid-window."
    return (f"Traditionally avoided for starting new things: {rahu.start:%H:%M} to {rahu.end:%H:%M} "
            f"(called Rahu Kaala), {place_label}.")


def render_brief(local_now: datetime, rahu, place_label: str, report: PanchangReport | None) -> str:
    """The morning message: date, the avoid-window, the Moon's day and star, any observance, the Tulu date."""
    today = local_now.date()
    lines = [f"🌅 Good morning! Today is {_day(today)}.", render_avoid_window(rahu, place_label)]
    if report is not None:
        f, tz = report.facts, report.tz
        # Sent between 6 and 9 am, possibly after an element has ended, so it is anchored to sunrise, as a panchang is.
        lines.append(f"At sunrise: the Moon's lunar day (tithi) {f.tithi.name}, {_until(f.tithi, tz, today)}; "
                     f"the Moon's star (nakshatra) {f.nakshatra.name}, {_until(f.nakshatra, tz, today)}.")
        for o in report.observances:
            lines += _observance_lines(o, today)
        lines.append(f"Tulu date: {report.tulu.month} {report.tulu.day}.")
    return "\n".join(lines)
