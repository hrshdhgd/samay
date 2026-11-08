"""Reports -> plain text for Telegram and the CLI. All user-facing wording lives in render/."""
from __future__ import annotations

from datetime import datetime

from ..engine.ephemeris import GRAHAS
from ..engine.vedic import NAKSHATRAS, RASHIS, SIGNS, house_from, nakshatra, sign_index
from ..models import NatalReport, NeedsDisambiguation, TodayReport

DISCLAIMER = "Traditional Jyotish interpretation, for reflection and fun — not a guarantee of events."
UNVALIDATED = "Not yet checked against reference software; treat positions as provisional."


def fmt_longitude(lon: float) -> str:
    s = sign_index(lon)
    n, p = nakshatra(lon)
    d = lon % 30
    return f"{SIGNS[s]} ({RASHIS[s]}) {int(d)}°{int(d % 1 * 60):02d}' · {NAKSHATRAS[n]} p{p}"


def _footer(report: NatalReport) -> list[str]:
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


def render_chart(report: NatalReport) -> str:
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
    return "\n".join(lines + _footer(report))


def render_dasha(report: NatalReport, now: datetime) -> str:
    lines = ["Vimshottari mahadashas:"]
    for p in report.dashas:
        mark = " ← now" if p.contains(now) else ""
        lines.append(f"{p.lord.title():8} {p.start:%b %Y} – {p.end:%b %Y}{mark}")
    return "\n".join(lines + _footer(report))


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


def render_today(report: TodayReport, reading: str | None = None) -> str:
    """Today's transits. `reading` replaces the plain fact list (e.g. reworded by narrate)."""
    body = reading if reading is not None else "\n".join(today_facts(report))
    return "\n".join([body, *_footer(report.natal)])


def render_options(d: NeedsDisambiguation) -> list[str]:
    """One line per option, in the same order as d.options."""
    if d.kind == "place":
        return [p.label for p in d.options]
    return [f"{'first' if i == 0 else 'second'} occurrence ({u:%H:%M} UTC)" for i, u in enumerate(d.options)]
