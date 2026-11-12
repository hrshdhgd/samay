"""Reports -> plain text for Telegram and the CLI. All user-facing wording lives in render/."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..engine.daylight import RahuKaala
from ..engine.entries import SERVABLE_LEVELS
from ..engine.ephemeris import GRAHAS
from ..engine.vedic import (
    DASHA_YEARS,
    NAKSHATRAS,
    RASHIS,
    SIGNS,
    Period,
    antardashas,
    house_from,
    nakshatra,
    sign_index,
)
from ..models import NatalReport, NeedsDisambiguation, OutlookReport, TodayReport
from ..qa import LIFE_AREAS, OUTLOOK_TOPICS
from ..subject import SELF
from . import prompts

DISCLAIMER = "Traditional Jyotish interpretation, for reflection and fun — not a guarantee of events."
UNVALIDATED = "Not yet checked against reference software; treat positions as provisional."
YOGA_SOURCES_PENDING = "ⓘ The book references for these yogas are still being checked."
OLD_CLOCKS = "⚠ Old clock records can be uncertain, so please double-check the birth time."


def fmt_longitude(lon: float) -> str:
    s = sign_index(lon)
    n, p = nakshatra(lon)
    d = lon % 30
    return f"{SIGNS[s]} ({RASHIS[s]}) {int(d)}°{int(d % 1 * 60):02d}' · {NAKSHATRAS[n]} p{p}"


def _family_footer(report: NatalReport) -> list[str]:
    """Short footer for chat: what was understood, a caution only when one applies, the disclaimer."""
    b, p = report.birth, report.birth.provenance
    lines = ["", f"Born {b.local:%d %b %Y, %H:%M} · {b.place.label}"]
    if p.warning:
        lines.append(f"⚠ {p.warning}")
    elif p.confidence == "low":
        lines.append(OLD_CLOCKS)
    if p.place_approximate and p.approx_note:
        lines.append(f"⚠ Place approximate: {p.approx_note}")
    return [*lines, DISCLAIMER, f"ref {report.stamp.code()}"]


def _footer(report: NatalReport, technical: bool = True) -> list[str]:
    """Technical footer (CLI): UTC conversion, time standard, profile and the full version stamp."""
    if not technical:
        return _family_footer(report)
    b = report.birth
    lines = [
        "",
        f"Born {b.local:%d %b %Y %H:%M} local, {b.place.label} → {b.utc:%Y-%m-%d %H:%M} UTC",
        f"Time standard: {b.provenance.offset_source} · confidence: {b.provenance.confidence}",
    ]
    if b.provenance.warning:
        lines.append(f"⚠ {b.provenance.warning}")
    if b.provenance.place_approximate and b.provenance.approx_note:
        lines.append(f"⚠ Place approximate: {b.provenance.approx_note}")
    lines.append(f"Profile: {report.stamp.profile_id} · ayanamsa {report.chart.ayanamsa:.4f}°")
    if not report.validated:
        lines.append(UNVALIDATED)
    lines += [f"[{report.stamp.short()}]", DISCLAIMER]
    return lines


def render_chart(report: NatalReport, technical: bool = True) -> str:
    c = report.chart
    lagna = sign_index(c.ascendant)
    lines = [f"Lagna: {fmt_longitude(c.ascendant)}", ""]
    for g in GRAHAS:
        pl = c.planets[g]
        h = house_from(lagna, sign_index(pl.longitude))
        retro = " ℞" if pl.retrograde and g not in ("rahu", "ketu") else ""
        lines.append(f"{g.title():8} H{h:<2} {fmt_longitude(pl.longitude)}{retro}")
    lines += ["", "Yogas:" if report.yogas else "No yogas from the current rule set."]
    for r in report.yogas:
        locus = f", {r.source['locus']}" if r.source.get("locus") else ""
        lines.append(f"• {r.name} — {r.effect} [{r.source['text']}{locus}]")
    if not technical and any(not r.source.get("verified") for r in report.yogas):
        lines.append(YOGA_SOURCES_PENDING)
    return "\n".join(lines + _footer(report, technical))


RAHU_KETU_NOTE = (
    "Rahu and Ketu are not planets you can see. They are the two points where the Moon's path "
    "crosses the Sun's path in the sky."
)


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _plain_dasha(report: NatalReport, now: datetime) -> list[str]:
    born = report.birth.utc
    lines = [
        "Your life chapters (dashas)",
        ("Jyotish divides time into chapters, each ruled by one planet. They follow a fixed order and "
        "last 6 to 20 years each; the full cycle is 120 years. Which chapter you began in depends on "
        "where the Moon was at your birth."),
        "",
    ]
    current = None
    for p in report.dashas:
        start = "birth" if p.start < born else f"{p.start:%b %Y}"
        mark = " ← now" if p.contains(now) else ""
        lines.append(f"{p.lord.title()} · {DASHA_YEARS[p.lord]} years · {start} – {p.end:%b %Y}{mark}")
        current = p if p.contains(now) else current
    lines += ["", RAHU_KETU_NOTE]
    if current is not None:
        lines += ["", f"Sub-chapters inside your {current.lord.title()} chapter:"]
        for a in antardashas(current):
            mark = " ← now" if a.contains(now) else ""
            lines.append(f"{a.lord.title()} · {a.start:%b %Y} – {a.end:%b %Y}{mark}")
    return lines


def render_dasha(report: NatalReport, now: datetime, technical: bool = True) -> str:
    if not technical:
        return "\n".join([*_plain_dasha(report, now), *_footer(report, technical)])
    lines = ["Vimshottari mahadashas:"]
    for p in report.dashas:
        mark = " ← now" if p.contains(now) else ""
        lines.append(f"{p.lord.title():8} {p.start:%b %Y} – {p.end:%b %Y}{mark}")
    return "\n".join(lines + _footer(report, technical))


def today_facts(report: TodayReport) -> list[str]:
    """The computed facts behind /today; the only thing an LLM is ever allowed to reword."""
    natal_moon = sign_index(report.natal.chart.planets["moon"].longitude)
    moon_now = fmt_longitude(report.sky.planets["moon"].longitude)
    facts = [f"Today ({report.now:%d %b %Y}). Natal Moon in {SIGNS[natal_moon]}; Moon now in {moon_now}."]
    for g, h in report.transit_houses:
        facts.append(f"Transiting {g.title()} is in house {h} from your Moon.")
    if report.current_dasha:
        maha, antar = report.current_dasha
        facts.append(f"Running {maha.lord.title()} mahadasha, {antar.lord.title()} antardasha.")
    return facts


def plain_today(report: TodayReport) -> list[str]:
    """Today's facts in everyday words: where the slow planets are, counted from the birth Moon
    sign, and which life chapter is running. No meanings, only computed facts."""
    moon_sign = sign_index(report.natal.chart.planets["moon"].longitude)
    lines = [
        (f"Your birth Moon sign is {SIGNS[moon_sign]} ({RASHIS[moon_sign]}). Jyotish counts signs "
        "from it: that sign is the 1st, the next is the 2nd, and so on."),
        "",
    ]
    for g, house in report.transit_houses:
        sign = sign_index(report.sky.planets[g].longitude)
        lines.append(f"{g.title()} is in {SIGNS[sign]} ({RASHIS[sign]}), the {ordinal(house)} sign from your Moon sign.")
    if report.current_dasha:
        maha, antar = report.current_dasha
        lines += [
            "",
            (f"You are in your {maha.lord.title()} life chapter (dasha), which lasts {DASHA_YEARS[maha.lord]} "
            f"years in all and runs until {maha.end:%b %Y}. Inside it you are in the {antar.lord.title()} "
            f"sub-chapter, until {antar.end:%d %b %Y}."),
        ]
    return lines


def render_today(
    report: TodayReport, reading: str | None = None, technical: bool = True, extras: tuple[str, ...] = ()
) -> str:
    """Today's transits. `reading` replaces the fact list (e.g. reworded by narrate); `extras` are
    further lines (such as Rahu Kaala). For chat (technical=False) the plain-words section comes
    first and the exact positions follow under "Technical details"."""
    if technical:
        body = reading if reading is not None else "\n".join(today_facts(report))
        return "\n".join([body, *extras, *_footer(report.natal, technical)])
    head = f"🌙 Today, {report.now:%A %d %B %Y}"
    if reading is not None:
        return "\n".join([head, reading, *extras, *_footer(report.natal, technical)])
    lines = [head, *plain_today(report), "", *extras, "", "Technical details", *today_facts(report)]
    return "\n".join([*lines, *_footer(report.natal, technical)])


def clock12(moment: datetime) -> str:
    """'8:00 am', rounded to the nearest minute."""
    moment += timedelta(seconds=30)
    return f"{moment.hour % 12 or 12}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"


def render_rahu_kaala(rahu: RahuKaala | None, place_label: str) -> str:
    if rahu is None:
        return prompts.NO_SUNRISE.format(place=place_label)
    return f"⚠ Rahu Kaala today: {clock12(rahu.start)} – {clock12(rahu.end)} ({place_label})"


def render_brief(
    local_now: datetime, rahu: RahuKaala | None, place_label: str, dasha: tuple[Period, Period] | None
) -> str:
    """The short morning message: date, Rahu Kaala, running dasha. Facts only, no meanings."""
    lines = [f"🌅 Good morning! Today is {local_now:%A, %d %B %Y}.", render_rahu_kaala(rahu, place_label)]
    if dasha:
        maha, antar = dasha
        lines.append(
            f"Running now: {maha.lord.title()} chapter (mahadasha) until {maha.end:%b %Y}, "
            f"{antar.lord.title()} sub-chapter (antardasha) until {antar.end:%d %b %Y}."
        )
    return "\n".join(lines)


def _ref(e) -> tuple[int, int, str]:
    """(chapter, first verse, label) for sorting and showing a citation such as '2.4–5' or '1.15 (note)'."""
    c = e.citation
    verse = str(c["verse"])
    head = verse.split(",")[0].strip()
    first = int(re.match(r"\d+", head).group())
    note = " (note)" if "note" in verse else ""
    return int(c["chapter"]), first, f"{c['chapter']}.{head.replace('-', '–')}{note}"


def sources_line(entries, reading=None, full: bool = False) -> str | None:
    """One line naming every source an answer used, in place of a citation after each entry."""
    groups: dict[str, set[tuple[int, int, str]]] = {}
    editions: dict[str, str] = {}
    for e in entries:
        groups.setdefault(e.citation["text"], set()).add(_ref(e))
        editions.setdefault(e.citation["text"], e.citation.get("edition", ""))
    levels = {e.verification.level for e in entries}
    if reading is not None:
        refs = groups.setdefault("Brihat Jataka", set())
        refs.update((20, v, f"20.{v}") for v in {x.verse for x in reading.effects} | {11})
        levels.add(reading.level)
    if not groups:
        return None
    parts = []
    for text, refs in groups.items():
        edition = f" ({editions[text]})" if full and editions.get(text) else ""
        parts.append(f"{text}{edition} " + ", ".join(label for _, _, label in sorted(refs)))
    status = "checked, some by a Sanskrit reader" if "sanskrit-checked" in levels else "checked"
    label = "Sources" if sum(len(r) for r in groups.values()) > 1 else "Source"
    return f"{label}: {'; '.join(parts)} · {status}"


def _render_verses(answer) -> str:
    """The Sanskrit view: each checked verse once, then one note that nobody fluent has proofread it."""
    verses, seen, unproofread = [], set(), False
    for e in answer.entries:
        if e.shows_verse and e.verse.devanagari not in seen:
            seen.add(e.verse.devanagari)
            unproofread = unproofread or not e.verse.proofread
            verses.append(f"{e.verse.devanagari}\n{e.verse.roman}\n({e.citation['text']} {_ref(e)[2]})")
    if not verses:
        return prompts.NO_SOURCE
    return "\n\n".join([*verses, *([prompts.VERSE_UNPROOFREAD] if unproofread else [])])


def render_answer(answer, view: str = "compact", birth_known: bool = True, ai_follows: bool = False) -> str:
    """A grounded answer. `view`: "compact" (the lead entry, the person's chart facts, one source line), "full"
    (every entry) or "sanskrit" (the checked verses)."""
    if answer.topic is None:
        return prompts.NO_TOPIC_AI if ai_follows else prompts.NO_TOPIC
    if answer.topic.startswith("future:") and not birth_known:
        return prompts.NEED_BIRTH_FOR_FUTURE
    if view == "sanskrit":
        return _render_verses(answer)
    full = view == "full"
    who = answer.who
    blocks: list[str] = [who.heading] if who.heading else []
    if who.minor:
        blocks.append(prompts.MINOR_NOTE)
    if answer.topic == "future:overview":
        blocks.append(prompts.FUTURE_TITLE.format(Your=who.Your))
    if answer.topic in OUTLOOK_TOPICS:
        if answer.outlook is not None:
            blocks.append(render_outlook(answer.outlook, full=full, who=who))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic.startswith("life:"):
        houses, label = LIFE_AREAS[answer.topic.split(":")[1]]
        which = " and ".join(ordinal(h) for h in houses)
        blocks.append(f"On {label}: Brihat Jataka reads this from the {which} house of the chart.\n{prompts.LIFE_FRAME.format(your=who.your)}")
    if answer.name_line:
        blocks.append(answer.name_line)
    shown = answer.entries if full else answer.entries[:1]
    if len(shown) > 1:
        blocks.append("\n".join(f"• {e.english}" for e in shown))
    elif shown:
        blocks.append(shown[0].english)
    if any(e.topic.startswith("dasha:") for e in shown):
        blocks.append(prompts.DASHA_FRAME)
    if not answer.entries and answer.topic != "future:overview":
        blocks.append(prompts.NO_SOURCE_AI if ai_follows else prompts.NO_SOURCE)
    blocks += list(answer.notes)
    if answer.reading is not None:
        blocks.append(render_reading(answer.reading, answer.shares, full=full, who=who))
    for reading, shares in answer.more_readings:
        blocks.append(render_reading(reading, shares, full=full, who=who))
    if answer.facts:
        facts = "\n".join(answer.facts)
        blocks.append(f"From {who.your} chart:\n{facts}" if full else facts)
    if not birth_known:
        blocks.append(prompts.NEED_BIRTH_FOR_FACTS)
    source = sources_line(shown, answer.reading or (answer.more_readings[0][0] if answer.more_readings else None), full)
    if source:
        blocks.append(source)
    blocks.append(DISCLAIMER)
    return "\n\n".join(blocks)


STRENGTH_WORDS = {
    "exaltation": "its exaltation sign (where the text counts it strongest)",
    "moolatrikona": "its moolatrikona sign",
    "own": "its own sign",
    "friendly": "a friend's sign",
    "neutral": "a neutral planet's sign",
    "inimical": "an enemy's sign",
    "depression": "its depression sign (where the text counts it weakest)",
}
STRENGTH_SHORT = {
    "exaltation": "its exaltation sign", "moolatrikona": "its moolatrikona sign", "own": "its own sign",
    "friendly": "a friend's sign", "neutral": "a neutral sign", "inimical": "an enemy's sign",
    "depression": "its depression sign",
}


def _share_phrase(label: str, share: str | None) -> str:
    if share is None:
        return f"it gives no share of the {label} effects here"
    if share == "not at all":
        return f"the {label} effects do not come to pass"
    if share == "fully":
        return f"the {label} effects come to pass in full"
    return f"{share} of the {label} effects come to pass"


def _rule_sentence(r, shares) -> str:
    """The text's own rule (20.11) on how much of the quoted effects applies, in one sentence."""
    if not shares.get("good") and not shares.get("bad"):
        return "The text's rule on how much applies gives no share for a neutral sign."
    kinds = {e.kind for e in r.effects}
    parts = [_share_phrase(label, shares.get(label)) for label in ("good", "bad") if kinds & {label, "mixed"}]
    return "By the text's own rule, " + "; ".join(parts) + "."


def render_reading(r, shares, full: bool = True, who=SELF) -> str:
    """Chapter XX on one planet in one house: the quoted lines, then the text's own strength rule."""
    name = r.planet.title()
    if not full:
        obscured = "; close to the Sun, so obscured" if r.astangata else ""
        lines = [f"{name} in {who.your} {ordinal(r.house)} house ({SIGNS[r.sign]}, {STRENGTH_SHORT[r.strength]}{obscured}):"]
        for e in r.effects:
            same = f" (the text gives {name} the same as {e.borrowed_from.title()} here)" if e.borrowed_from else ""
            lines.append(f"“{e.text}”{same}")
        lines.append(f"{_rule_sentence(r, shares)} {prompts.READING_FRAME_SHORT}")
        return "\n".join(lines)
    lines = [f"What Brihat Jataka chapter 20 says about {name} in {who.your} {ordinal(r.house)} house:"]
    for e in r.effects:
        borrowed = f" (the text gives {name} here the same effects as {e.borrowed_from.title()})" if e.borrowed_from else ""
        lines.append(f"“{e.text}”{borrowed}")
        if e.variant:
            lines.append(e.variant)
    where = f"{who.Your} {name} is in {SIGNS[r.sign]}, {STRENGTH_WORDS[r.strength]}"
    if r.astangata:
        where += ", and close enough to the Sun to be obscured (astangata)"
    lines += [where + ".", _rule_sentence(r, shares), prompts.READING_FRAME]
    return "\n".join(lines)


def render_ai(reply: str) -> str:
    """The AI's own answer, labelled so it is never mistaken for a sourced one."""
    return f"🤖 AI says: “{reply}”\n\n{prompts.AI_CAVEAT}"


def render_options(d: NeedsDisambiguation) -> list[str]:
    """One line per option, in the same order as d.options."""
    if d.kind == "place":
        return [p.label for p in d.options]
    return [f"{'first' if i == 0 else 'second'} occurrence ({u:%H:%M} UTC)" for i, u in enumerate(d.options)]


PLANET_ICONS = {"sun": "☀️", "moon": "🌙", "mars": "♂️", "mercury": "☿", "jupiter": "♃", "venus": "♀️", "saturn": "♄",
                "rahu": "☊", "ketu": "☋"}
OUTLOOK_TITLES = {"week": "{Your} week ahead", "fortnight": "{Your} next two weeks", "month": "{Your} month ahead",
                  "year": "{Your} year ahead", "years": "{Your} next five years"}


def _day(moment: datetime) -> str:
    return f"{moment.day} {moment:%b %Y}"


def _stamp(moment: datetime, tz: ZoneInfo, span: str) -> str:
    local = moment.astimezone(tz)
    if span in ("week", "fortnight"):
        return f"{local:%a} {local.day} {local:%b} {clock12(local).replace(':00', '')}"
    return f"{local.day} {local:%b}" if span == "month" else f"{local:%b %Y}"


def _stay_line(s, report: OutlookReport, tz: ZoneInfo, checked: bool, full: bool, chained: bool, repeat: bool) -> str:
    """One stay. As a bullet: 'Thu 12 Nov 3 am – Sat 14 Nov 4 pm · 1st ✓: the rise of good fortune'. Chained after
    the planet's name ('9th ✓ until Mar 2027: ...; then 10th: ...'), each part starts where the last one ended.
    `repeat`: the planet was in this house earlier in the period (it turned back), so its result is not repeated."""
    span = report.span
    house = f"{ordinal(s.house)}{' ✓' if checked and s.favourable else ''}"
    if chained:
        line = house + (f" until {_stamp(s.end, tz, span)}" if s.end is not None else "")
    else:
        since = "now" if s.start is None else _stamp(s.start, tz, span)
        until = "end" if s.end is None else _stamp(s.end, tz, span)
        line = f"{since} – {until} · {house}"
    if s.effect and not repeat:
        line += f": {s.effect}"
    if checked and s.blocked_by:
        line += f" ⛔ blocked by {' and '.join(g.title() for g in s.blocked_by)} in the {ordinal(s.vedha_house)} (vedha)"
    elif checked and full and s.vedha_house and s.effect and not repeat:
        line += f" (unless a planet is in the {ordinal(s.vedha_house)}: vedha)"
    return line


def render_outlook(report: OutlookReport, full: bool = False, who=SELF) -> str:
    """The period ahead: the running dasha and any sub-chapter that begins, then each planet's houses from the Moon
    sign with Phaladeepika chapter 26's result for it. Without a checked rules file, positions only."""
    tz = ZoneInfo(report.tz)
    checked = report.rules_level in SERVABLE_LEVELS
    start, end = report.start.astimezone(tz), report.end.astimezone(tz)
    lines = [f"🔮 {OUTLOOK_TITLES[report.span].format(Your=who.Your)}: {_day(start)} – {_day(end)}",
             f"Counted from {who.your} Moon sign, {SIGNS[report.moon_sign]} ({RASHIS[report.moon_sign]})."]
    if report.dasha_at_start:
        maha, antar = report.dasha_at_start
        lines.append(f"⏳ {maha.lord.title()} chapter, {antar.lord.title()} sub-chapter until {_day(antar.end)}.")
    lines += [f"⏳ From {_day(a.start)}: {a.lord.title()} sub-chapter of the "
              f"{lord.title()} chapter." for lord, a in report.dasha_changes]
    body = []
    by_planet: dict[str, list] = {}
    for s in report.stays:
        by_planet.setdefault(s.planet, []).append(s)
    for planet, stays in by_planet.items():
        name = f"{PLANET_ICONS[planet]} {planet.title()}"
        repeats = [any(t.house == s.house for t in stays[:i]) for i, s in enumerate(stays)]
        if planet == "moon" or (full and len(stays) > 1):
            body.append(name + "\n" + "\n".join(f"• {_stay_line(s, report, tz, checked, full, False, r)}"
                                                for s, r in zip(stays, repeats, strict=True)))
        else:
            body.append(f"{name}: " + "; then ".join(_stay_line(s, report, tz, checked, full, True, r)
                                                     for s, r in zip(stays, repeats, strict=True)))
    blocks = ["\n".join(lines), "\n".join(body)]
    if checked:
        blocks.append(prompts.OUTLOOK_KEY)
        if full:
            blocks.append(prompts.OUTLOOK_NOT_APPLIED)
        verses = sorted({s.verse for s in report.stays if s.verse}, key=lambda v: int(v.split("-")[0]))
        blocks.append(f"{prompts.OUTLOOK_FRAME}\n\nSource: Phaladeepika 26.2–8, " + ", ".join(f"26.{v.replace('-', '–')}" for v in verses)
                      + (f" ({report.rules_edition}, pp. {report.rules_pages})" if full else "") + " · checked")
    else:
        blocks.append(prompts.OUTLOOK_UNCHECKED)
    return "\n\n".join(blocks)
