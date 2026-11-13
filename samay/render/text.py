"""Reports -> plain text for Telegram and the CLI. All user-facing wording lives in render/."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..engine import conjunctions, health, house_timing
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

TELEGRAM_LIMIT = 4096


def split_message(text: str, limit: int = 4000) -> list[str]:
    """The text as one or more messages, none longer than Telegram allows, cut at a blank line when possible, else at a
    line, else at a space. Nothing is dropped or reworded."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        for piece in _pieces(para, limit):
            joined = f"{current}\n\n{piece}" if current else piece
            if len(joined) <= limit:
                current = joined
            else:
                chunks.append(current)
                current = piece
    chunks.append(current)
    return chunks


def _pieces(para: str, limit: int) -> list[str]:
    """A paragraph that fits as is, else its lines, else its words, each short enough."""
    if len(para) <= limit:
        return [para]
    out, current = [], ""
    for line in para.split("\n"):
        for part in ([line] if len(line) <= limit else _words(line, limit)):
            joined = f"{current}\n{part}" if current else part
            if len(joined) <= limit:
                current = joined
            else:
                out.append(current)
                current = part
    return [*out, current]


def _words(line: str, limit: int) -> list[str]:
    out, current = [], ""
    for word in line.split(" "):
        joined = f"{current} {word}" if current else word
        if len(joined) <= limit:
            current = joined
        else:
            if current:
                out.append(current)
            current = word[:limit]
    return [*out, current]


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


def sources_line(entries, reading=None, full: bool = False, second=(), lordship=()) -> str | None:
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
    for v in second:
        first = int(v.verse.split("-")[0])
        groups.setdefault("Phaladeepika", set()).add((8, first, f"8.{v.verse.replace('-', '–')}"))
    for v in lordship:
        for verse in [*(r[2] for r in v.rows), *(n[0] for n in v.nature), *(n[0] for n in v.troublesome)]:
            groups.setdefault("Phaladeepika", set()).add((20, verse, f"20.{verse}"))
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
    if answer.topic == "chart:ashtakavarga" and not birth_known:
        return prompts.NEED_BIRTH_FOR_CHART
    if answer.topic == "chart:moon" and not birth_known:
        return prompts.NEED_BIRTH_FOR_MOON
    if answer.topic == "chart:conjunctions" and not birth_known:
        return prompts.NEED_BIRTH_FOR_TOGETHER
    if answer.topic == "chart:yogas" and not birth_known:
        return prompts.NEED_BIRTH_FOR_YOGAS
    if answer.topic.startswith("when:") and not birth_known:
        return prompts.NEED_BIRTH_FOR_WHEN
    if answer.topic == "chart:health" and not birth_known:
        return prompts.NEED_BIRTH_FOR_HEALTH
    if view == "sanskrit":
        return _render_verses(answer)
    full = view == "full"
    who = answer.who
    blocks: list[str] = [who.heading] if who.heading else []
    if who.minor:
        blocks.append(prompts.MINOR_NOTE)
    if answer.topic == "future:overview":
        blocks.append(prompts.FUTURE_TITLE.format(Your=who.Your))
    if answer.topic == "chart:health":
        blocks.append(render_health(answer, who, full))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic.startswith("when:"):
        blocks.append(render_timing(answer, who, full))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic == "chart:yogas":
        blocks.append(render_yogas(answer.yogas, who, full))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic == "chart:conjunctions":
        blocks.append(render_together(answer, who, full))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic == "chart:moon":
        if answer.moon is not None:
            blocks.append(render_moon(answer.moon, full=full, who=who))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic == "chart:ashtakavarga":
        if answer.ashtaka is not None:
            blocks.append(render_ashtaka(answer.ashtaka, full=full, who=who))
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks)
    if answer.topic in OUTLOOK_TOPICS:
        if answer.outlook is not None:
            blocks.append(render_outlook(answer.outlook, full=True, who=who) if full else render_outlook_plain(answer.outlook, who))
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
    for voice in answer.second:
        blocks.append(render_second(voice, who))
    for verdict in answer.lordship:
        blocks.append(render_lordship(verdict, who, full))
    if answer.facts:
        facts = "\n".join(answer.facts)
        blocks.append(f"From {who.your} chart:\n{facts}" if full else facts)
    if not birth_known:
        blocks.append(prompts.NEED_BIRTH_FOR_FACTS)
    source = sources_line(shown, answer.reading or (answer.more_readings[0][0] if answer.more_readings else None), full,
                          answer.second, answer.lordship)
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


def _span(a: datetime, b: datetime, tz: ZoneInfo) -> str:
    x, y = a.astimezone(tz), b.astimezone(tz)
    return f"{_day(x)}" if (x.year, x.month, x.day) == (y.year, y.month, y.day) else f"{_day(x)} – {_day(y)}"


def _rule_line(r, tz: ZoneInfo, limit: int) -> str:
    if r.note:
        return f"• {r.text[0].upper()}{r.text[1:]} ({r.verse}): {r.note}."
    head = f"• {r.text[0].upper()}{r.text[1:]} ({r.verse}):"
    if not r.windows:
        return f"{head} not in this period."
    if r.total and r.days / r.total > 0.5:
        return f"{head} {prompts.WHEN_ALL_DAY.format(pct=round(100 * r.days / r.total))}."
    shown = ", ".join(_span(a, b, tz) for a, b in r.windows[:limit])
    more = f" and {len(r.windows) - limit} more" if len(r.windows) > limit else ""
    return f"{head} {shown}{more} ({r.days} of {r.total} days)."


def render_health(answer, who=SELF, full: bool = False) -> str:
    """The sources of disease in the chart by Phaladeepika 14.1, what each stands for, where they agree, and the specific combinations."""
    title = f"🩺 What Phaladeepika's disease rules point to in {who.your} chart"
    rules = health.load_rules()
    if not answer.health_checked:
        return f"{title}\n\n{prompts.HEALTH_UNCHECKED}\n\n{rules.caution}"
    h = answer.health
    if h is None:
        return f"{title}\n\n{prompts.NEED_BIRTH_FOR_HEALTH}"
    blocks = [title, rules.caution]
    if not h.sources:
        blocks.append(prompts.HEALTH_NONE)
    else:
        lines = [f"Sources of disease (14.1: {rules.sources_text.split(' A particular')[0].lower()}):"]
        for s in h.sources:
            items = [t for t, _ in s.items]
            shown = items if full else items[:6]
            more = f"; and {len(items) - len(shown)} more (tap More)" if len(shown) < len(items) else ""
            lines.append(f"• {s.planet.title()} ({'; '.join(s.why)}), which stands for: {'; '.join(shown)}{more}.")
        blocks.append("\n".join(lines))
        if h.overlaps:
            joined = "; ".join(f"{tag} ({', '.join(p.title() for p in ps)})" for tag, ps in h.overlaps)
            blocks.append(f"Where two or more of these point to the same kind of trouble (the book says such a trouble may be predicted): {joined}.")
    if h.combinations:
        lines = ["The book's specific combinations found in the chart (14.10–11):"]
        lines += [f"• {c.text[0].upper()}{c.text[1:]} ({c.detail})." for c in h.combinations]
        blocks.append("\n".join(lines))
    verses = sorted({s.verse for s in h.sources} | {c.verse for c in h.combinations} | {rules.sources_verse}, key=lambda v: int(v.split(".")[1]))
    blocks.append("Source: Phaladeepika " + ", ".join(verses) + (f" ({rules.edition}, pp. {rules.pages})" if full else "") + " · checked")
    return "\n\n".join(blocks)


def render_timing(answer, who=SELF, full: bool = False) -> str:
    """When a life area may bear fruit, by Phaladeepika's own conditions, as stretches of the next three years. Never a date."""
    area = answer.topic.split(":")[1]
    label = LIFE_AREAS[area][1]
    title = f"⏳ When might {label} come into play for {who.name if not who.is_self else 'you'}?"
    if not answer.timing_checked:
        return f"{title}\n\n{prompts.WHEN_UNCHECKED}"
    t = answer.timing
    if t is None:
        return f"{title}\n\n{prompts.NEED_BIRTH_FOR_WHEN}"
    rules = house_timing.load_rules()
    tz = ZoneInfo(t.tz)
    limit = 8 if full else 4
    blocks = [title, f"{rules.frame} ({_day(t.start.astimezone(tz))} – {_day(t.end.astimezone(tz))}.)"]
    if t.marriage:
        m1, _, m3 = t.marriage
        lines = ["Marriage, from Phaladeepika chapter 10:"]
        main = _rule_line(m3, tz, limit).split("): ", 1)[1]
        lines.append(f"• While the strongest of the 7th lord's rulers, Venus and the Moon ({', '.join(p.title() for p in t.m3_planets)}) "
                     f"is running its dasha and Jupiter is in a trikona from the 7th lord's sign or navamsa (10.14): {main}")
        lines.append(f"• The dasha of a planet in, aspecting or ruling the 7th ({', '.join(p.title() for p in t.m2_planets)}) (10.13):")
        lines += [f"   – {d.lord.title()} {d.kind}{'' if d.kind == 'mahadasha' else ' in the ' + d.maha.title() + ' mahadasha'}: "
                  f"{_span(max(d.start, t.start), min(d.end, t.end), tz)}" for d in t.dashas[: 2 * limit]]
        if not t.dashas:
            lines.append("   – none begins or runs in this period.")
        lines.append(_rule_line(m1, tz, limit))
        blocks.append("\n".join(lines))
    houses = ", ".join(ordinal(h) for h in t.houses)
    for ref in ("lagna", "the Moon sign"):
        rs = [r for r in t.general if r.ref == ref]
        if not rs:
            continue
        lines = [f"For the {houses} house, counted from the {ref} (chapter 16.31–35):"]
        lines += [f"{'[' + ordinal(r.house) + '] ' if len(t.houses) > 1 else ''}{_rule_line(r, tz, limit)}" for r in rs]
        blocks.append("\n".join(lines))
    verses = sorted({r.verse for r in (*t.marriage, *t.general)}, key=lambda v: (int(v.split(".")[0]), int(v.split(".")[1])))
    edition = f" ({rules.edition}, pp. {rules.pages})" if full else ""
    blocks.append(f"{rules.moon_note}\n\nSource: Phaladeepika {', '.join(verses)}{edition} · checked")
    return "\n\n".join(blocks)


def render_yogas(view, who=SELF, full: bool = False) -> str:
    """Yogas from Brihat Jataka 12 (Nabhasa), Phaladeepika 6 and Brihat Jataka 11 (raja), each only once its own file is checked."""
    blocks = [f"🧭 {who.Your} yogas"]
    nab = view.nabhasa
    if nab.checked:
        count = f"{nab.sign_count} sign{'s' if nab.sign_count > 1 else ''}"
        lines = [f"Nabhasa yogas (Brihat Jataka chapter 12), made by where the seven planets sit ({count}):"]
        for y in nab.yogas:
            lines.append(f"• {y.name} ({y.detail}): “A person born under it {y.text}”" + (f" {y.variant}" if y.variant and full else ""))
        lines.append(f"{nab.life_note}" + (f" {nab.life_except}" if full else ""))
        refs = sorted({y.verse for y in nab.yogas} | {nab.life_verse}, key=lambda v: int(v.split(".")[1]))
        lines.append("Source: Brihat Jataka " + ", ".join(refs) + " · checked")
        blocks.append("\n".join(lines))
    else:
        blocks.append(prompts.YOGAS_UNCHECKED + " (Nabhasa yogas, Brihat Jataka chapter 12)")
    if view.chapter6_checked:
        lines = [f"Yogas from Phaladeepika chapter 6, found in {who.your} chart:"]
        for f in view.chapter6:
            lines.append(f"• {f.name} ({f.detail}): {f.text[0].upper()}{f.text[1:]}.")
        lines.append(view.blemish_note)
        lines.append("Source: Phaladeepika " + ", ".join(sorted({f.verse for f in view.chapter6}, key=lambda v: int(v.split(".")[1].split("–")[0]))) + " · checked")
        blocks.append("\n".join(lines))
    else:
        blocks.append(prompts.YOGAS_UNCHECKED + " (Phaladeepika chapter 6)")
    if view.raja_checked:
        if view.raja:
            lines = ["Raja yogas of Brihat Jataka chapter 11:"]
            for f in view.raja:
                lines.append(f"• {f.detail}: “{f.text}”" + (f" {f.family_note}" if f.family_note and full else ""))
            lines.append("Source: Brihat Jataka " + ", ".join(sorted({f.verse for f in view.raja})) + " · checked")
            blocks.append("\n".join(lines))
        else:
            blocks.append(prompts.YOGAS_NONE_RAJA)
    else:
        blocks.append(prompts.YOGAS_UNCHECKED + " (raja yogas, Brihat Jataka chapter 11)")
    return "\n\n".join(blocks)


def render_together(answer, who=SELF, full: bool = False) -> str:
    """Planets sharing a sign, pair by pair: Brihat Jataka quoted, Phaladeepika paraphrased, both with their verses."""
    title = f"🪐 Planets together in {who.your} chart"
    if not answer.together_checked:
        return f"{title}\n\n{prompts.TOGETHER_UNCHECKED}"
    if not answer.together:
        return f"{title}\n\n{prompts.TOGETHER_NONE}"
    blocks = [title]
    for t in answer.together:
        names = " and ".join(p.title() for p in t.planets) if len(t.planets) < 3 else ", ".join(p.title() for p in t.planets)
        lines = [f"{names} in {SIGNS[t.sign]} ({RASHIS[t.sign]}):"]
        for (a, b), p in t.pairs:
            lines.append(f"• {a.title()} with {b.title()}. Brihat Jataka {p.verse_bj}: “the person will be {p.bj}.” "
                         f"Phaladeepika {p.verse_pd}: {p.pd[0].upper()}{p.pd[1:]}.")
            if p.bj_note and full:
                lines.append(f"  ({p.bj_note})")
        blocks.append("\n".join(lines))
    if any(len(t.planets) > 2 for t in answer.together):
        blocks.append(f"With more than two planets in one sign, each pair is read in turn: “{conjunctions.load_rules().three_bj}”")
    verses = sorted({v for t in answer.together for _, p in t.pairs for v in (p.verse_bj, p.verse_pd)})
    named = [f"{name} {', '.join(v for v in verses if v.startswith(prefix))}"
             for name, prefix in (("Brihat Jataka", "14"), ("Phaladeepika", "18")) if any(v.startswith(prefix) for v in verses)]
    blocks.append("Source: " + "; ".join(named) + " · checked")
    return "\n\n".join(blocks)


def render_moon(view, full: bool = False, who=SELF) -> str:
    """The Moon's sign and nakshatra and what Brihat Jataka says of a person born so, the lunar yogas of chapter XIII,
    and the text's own conditions. Each part appears only once its own rules file has been checked."""
    head = (f"🌙 {who.Your} Moon is in {SIGNS[view.sign]} ({RASHIS[view.sign]}), in the nakshatra "
            f"{NAKSHATRAS[view.nakshatra_index]}, pada {view.pada}.")
    blocks = [head]
    refs = []
    if view.checked:
        blocks.append("\n".join([
            f"What Brihat Jataka says of a person born with the Moon in {SIGNS[view.sign]} (chapter 17.{view.sign_text.verse}):",
            f"“{view.sign_text.text[0].upper()}{view.sign_text.text[1:]}”", "",
            f"…and in {view.nakshatra.name} (chapter 16.{view.nakshatra.verse}):",
            f"“{view.nakshatra.text[0].upper()}{view.nakshatra.text[1:]}”"]))
        cond = f"The text adds: {view.conditions['sign'][1]} {view.conditions['nakshatra'][1]}"
        if full:
            cond += f"\n{view.conditions['sign_translators_note'][1]} (the translator's note)"
        blocks.append(cond)
        refs += [f"16.{view.nakshatra.verse}", f"17.{view.sign_text.verse}", "17.13"]
    else:
        blocks.append(prompts.MOON_UNCHECKED)
    if view.yogas_checked:
        lines = [f"The Moon's yogas in {who.your} chart (Brihat Jataka chapter 13):"]
        for f in view.yogas:
            lines.append(f"• {f.name}" + (f" ({f.detail})" if f.detail else "") + f": “{f.text[0].upper()}{f.text[1:]}”")
            lines += [f"  {note}" for note in f.extra if full or f.name.startswith("Kemadruma")]
        blocks.append("\n".join(lines))
        refs += sorted({f.verse for f in view.yogas}, key=lambda v: int(v.split(".")[1].split("–")[0]))
    else:
        blocks.append(prompts.MOON_YOGAS_UNCHECKED)
    if view.aspects_checked and view.aspects is not None:
        a = view.aspects
        if not a.aspecting:
            blocks.append(prompts.MOON_NOT_ASPECTED)
        else:
            lines = [f"{who.Your} Moon is aspected by {', '.join(p.title() for p in a.aspecting)} (Brihat Jataka chapter 19):"]
            lines += [f"• In {a.sign}, aspected by {p.title()}: “the person will {t}.”" for p, t in a.in_sign]
            lines += [f"• In the navamsa of {a.navamsa_lord.title()} ({a.navamsa_sign}), aspected by {p.title()}: “the person will {t}.”"
                      for p, t in a.in_navamsa]
            if full:
                lines += [view.aspect_texts[1], view.aspect_texts[2]]
            blocks.append("\n".join(lines))
            refs += ["19.1–3", "19.5–8"] + (["19.9"] if full else [])
    else:
        blocks.append(prompts.MOON_ASPECTS_UNCHECKED)
    if refs:
        editions = f" ({view.edition}, pp. {view.pages}; yogas pp. {view.yoga_pages})" if full else ""
        blocks.append(f"Source: Brihat Jataka {', '.join(dict.fromkeys(refs))}{editions} · checked")
    return "\n\n".join(blocks)


def render_ashtaka(view, full: bool = False, who=SELF) -> str:
    """The sign totals, by house from the lagna, with the text's 28 rule; per-planet points in the full view."""
    title = f"🔢 {who.Your} ashtakavarga (benefic points per sign)"
    if not view.checked:
        return f"{title}\n\n{prompts.ASHTAKA_UNCHECKED}"
    lines = [title, ""]
    for h in range(1, 13):
        sign = (view.lagna + h - 1) % 12
        n = view.sarva[sign]
        row = f"{ordinal(h)} house · {SIGNS[sign]} ({RASHIS[sign]}): {n}{' ✓' if n > view.threshold else ''}"
        if full:
            row += "  [" + ", ".join(f"{p.title()} {view.bhinna[p][sign]}" for p in view.bhinna) + "]"
        lines.append(row)
    rule = (f"The text (Phaladeepika {view.verse}) says a transit through a sign with more than {view.threshold} points "
            f"is {view.above}; with fewer, it brings {view.below}.")
    lines += ["", f"Together {sum(view.sarva)} points. {prompts.ASHTAKA_KEY}", rule]
    if full:
        lines.append(f"Counted with Brihat Jataka's tables (also the standard modern ones); Phaladeepika's English translation "
                     f"prints different lists in {view.variants} of the 56 ({view.edition}; {view.pages}).")
    lines.append(f"Source: Brihat Jataka 9.1–7; Phaladeepika {view.verse} · checked")
    return "\n".join(lines)


def render_lordship(v, who=SELF, full: bool = False) -> str:
    """Phaladeepika chapter 20 for one planet: the houses it rules in this chart, how it stands by verse 14, and the text's result."""
    rules = " and ".join(ordinal(h) for h in v.owned)
    head = (f"What Phaladeepika chapter 20 says of the {v.planet.title()} dasha, as the lord of {who.your} {rules} house "
            f"({v.planet.title()} stands in the {ordinal(v.house)}):")
    lines = [head]
    notes = []
    if v.adverse:
        notes.append("the text counts against it: " + ", ".join(v.adverse))
    if v.good:
        notes.append("the text counts for it: " + ", ".join(v.good))
    if notes:
        lines.append("; ".join(notes).capitalize() + ".")
    if v.leaning == "undecided":
        lines.append(prompts.LORDSHIP_UNDECIDED)
    for h, kind, _, text in v.rows:
        tag = {"strong": "if strong", "weak": "if weak", "both": ""}[kind] if v.leaning == "undecided" else ""
        lines.append(f"• {ordinal(h)} house{f' ({tag})' if tag else ''}: {text[0].upper()}{text[1:]}.")
    if v.nature:
        lines.append(f"Parasara's view, as the text gives it (20.{v.nature[0][0]}):")
        lines += [f"• {t[0].upper()}{t[1:]}." for _, t in v.nature]
    if v.troublesome:
        lines.append(f"Dashas the text says bring misery and trouble (20.{v.troublesome[0][0]}), and this one is among them:")
        lines += [f"• {t[0].upper()}{t[1:]}." for _, t in v.troublesome]
    return "\n".join(lines)


def render_second(v, who=SELF) -> str:
    """Phaladeepika chapter 8 on one planet in one house: the paraphrased results, a rising-sign line where the text has one."""
    lines = [f"What Phaladeepika chapter 8 says about {v.planet.title()} in {who.your} {ordinal(v.house)} house:"]
    for r in v.rows:
        prefix = f"With {' or '.join(SIGNS[i] for i in sorted(r.when_lagna))} rising: " if r.when_lagna else ""
        lines.append(f"{prefix}{r.text[0].upper()}{r.text[1:]}.")
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
    if report.ashtaka_checked and s.points is not None:
        meaning = dict(report.ashtaka_meaning).get(s.points) if full else None
        house += f" ({s.points} pts{f': {meaning}' if meaning else ''})"
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


def render_outlook_plain(report: OutlookReport, who=SELF) -> str:
    """The period ahead in everyday words: the life chapter, when things change, and (once the book's meanings are checked) what each
    stretch is said to bring, as good or hard for that planet. Houses, points and verse numbers are in the technical view."""
    tz = ZoneInfo(report.tz)
    checked = report.rules_level in SERVABLE_LEVELS
    start, end = report.start.astimezone(tz), report.end.astimezone(tz)
    lines = [f"🔮 {OUTLOOK_TITLES[report.span].format(Your=who.Your)}: {_day(start)} – {_day(end)}"]
    if report.dasha_at_start:
        maha, antar = report.dasha_at_start
        lines.append(f"{who.you_are.capitalize()} in the {maha.lord.title()} chapter of life, in its {antar.lord.title()} sub-chapter "
                     f"until {_day(antar.end)}.")
    said = {(m, a): text for m, a, text, _ in report.antardasha}
    if report.dasha_at_start and (report.dasha_at_start[0].lord, report.dasha_at_start[1].lord) in said:
        lines.append(f"The old book says of this sub-chapter: {said[report.dasha_at_start[0].lord, report.dasha_at_start[1].lord]}.")
    for lord, a in report.dasha_changes:
        lines.append(f"A new sub-chapter ({a.lord.title()}, in the {lord.title()} chapter) begins on {_day(a.start)}."
                     + (f" The book says of it: {said[lord, a.lord]}." if (lord, a.lord) in said else ""))
    blocks = ["\n".join(lines)]
    moves = sorted((s.start, s.planet) for s in report.stays if s.start is not None)
    stay = [s.planet for s in report.stays if s.planet not in {p for _, p in moves}]
    if moon := [t for t, p in moves if p == "moon"]:
        times = ", ".join(_stamp(t, tz, report.span) for t in moon)
        blocks.append(f"🌙 The Moon changes house every couple of days, so it is what shifts the mood through the week: it moves on {times}.")
    others = [(t, p) for t, p in moves if p != "moon"]
    if others:
        blocks.append("Other planets that change house in this time: " + "; ".join(
            f"{PLANET_ICONS[p]} {p.title()} on {_stamp(t, tz, report.span)}" for t, p in others[:10]) + (" …" if len(others) > 10 else "") + ".")
    if stay and report.span in ("week", "fortnight", "month"):
        blocks.append("Staying where they are the whole time: " + ", ".join(f"{PLANET_ICONS[p]} {p.title()}" for p in dict.fromkeys(stay)) + ".")
    if not checked:
        blocks.append("What the old book says these planet positions bring is still waiting for a check, so I am not saying what they mean yet.")
    else:
        lines = []
        by_planet: dict[str, list] = {}
        for s in report.stays:
            by_planet.setdefault(s.planet, []).append(s)
        for planet, stays in by_planet.items():
            keep = 6 if planet == "moon" else 3
            shown = stays[:keep]
            for s in shown:
                if not s.effect:
                    continue
                if s.favourable is None:
                    verdict = ""
                else:
                    verdict = "a good stretch" if s.favourable else "a hard stretch"
                    if s.blocked_by:
                        verdict += f" (its good result is held back by {' and '.join(g.title() for g in s.blocked_by)})"
                first = "now" if s.start is None else _stamp(s.start, tz, report.span)
                last = "the end" if s.end is None else _stamp(s.end, tz, report.span)
                when = "all through" if s.start is None and s.end is None else f"{first} – {last}"
                lines.append(f"{PLANET_ICONS[planet]} {planet.title()}, {when}: {verdict + ': ' if verdict else ''}{s.effect}.")
            if len(stays) > keep:
                n = len(stays) - keep
                lines.append(f"   …and {n} more change{'s' if n > 1 else ''} for {planet.title()} (see the technical details).")
        if lines:
            blocks.append("What the old book says each stretch brings:\n" + "\n".join(lines))
        verses = sorted({s.verse for s in report.stays if s.verse}, key=lambda v: int(v.split("-")[0]))
        refs = ["26.2–8", *(f"26.{v.replace('-', '–')}" for v in verses)]
        if report.antardasha_checked:
            refs += [f"21.{verse}" for _, _, _, verse in sorted(report.antardasha, key=lambda r: r[3])]
        blocks.append(f"{prompts.OUTLOOK_FRAME}\n\nSource: Phaladeepika {', '.join(refs)} · checked")
    blocks.append(prompts.OUTLOOK_TECH_HINT)
    return "\n\n".join(blocks)


def render_outlook(report: OutlookReport, full: bool = False, who=SELF) -> str:
    """The period ahead: the running dasha and any sub-chapter that begins, then each planet's houses from the Moon
    sign with Phaladeepika chapter 26's result for it. Without a checked rules file, positions only."""
    tz = ZoneInfo(report.tz)
    checked = report.rules_level in SERVABLE_LEVELS
    start, end = report.start.astimezone(tz), report.end.astimezone(tz)
    lines = [f"🔮 {OUTLOOK_TITLES[report.span].format(Your=who.Your)}: {_day(start)} – {_day(end)}",
             f"Counted from {who.your} Moon sign, {SIGNS[report.moon_sign]} ({RASHIS[report.moon_sign]})."]
    said = {(m, a): text for m, a, text, _ in report.antardasha}

    def result(maha: str, antar: str) -> str:
        return f"\n    The text: {said[maha, antar]}." if (maha, antar) in said else ""

    if report.dasha_at_start:
        maha, antar = report.dasha_at_start
        lines.append(f"⏳ {maha.lord.title()} chapter, {antar.lord.title()} sub-chapter until {_day(antar.end)}."
                     + result(maha.lord, antar.lord))
    lines += [f"⏳ From {_day(a.start)}: {a.lord.title()} sub-chapter of the {lord.title()} chapter."
              + result(lord, a.lord) for lord, a in report.dasha_changes]
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
    refs, editions = [], []
    if checked:
        blocks.append(prompts.OUTLOOK_KEY)
        if full:
            blocks.append(prompts.OUTLOOK_NOT_APPLIED)
        verses = sorted({s.verse for s in report.stays if s.verse}, key=lambda v: int(v.split("-")[0]))
        refs += ["26.2–8", *(f"26.{v.replace('-', '–')}" for v in verses)]
        editions.append(f"pp. {report.rules_pages}")
    else:
        blocks.append(prompts.OUTLOOK_UNCHECKED)
    if report.antardasha_checked:
        refs += [f"21.{verse}" for _, _, _, verse in sorted(report.antardasha, key=lambda r: r[3])]
        editions.append(f"pp. {report.antardasha_pages}")
    else:
        blocks.append(prompts.OUTLOOK_DASHA_UNCHECKED)
    if report.ashtaka_checked and any(s.points is not None for s in report.stays):
        refs += ["23.11"]
        if full:
            blocks.append(prompts.OUTLOOK_ASHTAKA_NOTE.format(n=report.ashtaka_variants))
    if refs:
        edition = f" ({report.rules_edition}; {', '.join(editions)})" if full else ""
        more = "; Brihat Jataka 9.1–7" if report.ashtaka_checked and any(s.points is not None for s in report.stays) else ""
        blocks.append(f"{prompts.OUTLOOK_FRAME}\n\nSource: Phaladeepika {', '.join(refs)}{more}{edition} · checked")
    return "\n\n".join(blocks)
