"""Reports -> plain text for Telegram and the CLI. All user-facing wording lives in render/."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..engine.daylight import RahuKaala
from ..engine.ephemeris import GRAHAS
from ..engine.vedic import NAKSHATRAS, RASHIS, SIGNS, Period, house_from, nakshatra, sign_index
from ..models import NatalReport, NeedsDisambiguation, TodayReport
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


def render_dasha(report: NatalReport, now: datetime, technical: bool = True) -> str:
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


def render_today(
    report: TodayReport, reading: str | None = None, technical: bool = True, extras: tuple[str, ...] = ()
) -> str:
    """Today's transits. `reading` replaces the plain fact list (e.g. reworded by narrate);
    `extras` are further lines shown before the footer (such as Rahu Kaala)."""
    body = reading if reading is not None else "\n".join(today_facts(report))
    return "\n".join([body, *extras, *_footer(report.natal, technical)])


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


def render_options(d: NeedsDisambiguation) -> list[str]:
    """One line per option, in the same order as d.options."""
    if d.kind == "place":
        return [p.label for p in d.options]
    return [f"{'first' if i == 0 else 'second'} occurrence ({u:%H:%M} UTC)" for i, u in enumerate(d.options)]
