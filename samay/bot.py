"""Telegram bot (long polling: no public port, domain or TLS needed)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import db
from .ephemeris import GRAHAS, compute_chart
from .geo import find_place, local_to_utc
from .narrate import narrate
from .rules import fired, load_rules
from .vedic import NAKSHATRAS, RASHIS, SIGNS, current_dasha, house_from, nakshatra, sign_index

log = logging.getLogger("samay")
RULES = load_rules()
DISCLAIMER = "Traditional Jyotish interpretation, for reflection and fun — not a guarantee of events."

HELP = (
    "Namaste, I'm samay.\n\n"
    "/birth DD-MM-YYYY HH:MM City[, CC]  — e.g. /birth 15-08-1990 14:30 Pune, IN\n"
    "/chart — your sidereal (Lahiri) birth chart and yogas\n"
    "/dasha — current Vimshottari mahadasha / antardasha\n"
    "/today — today's transits relative to your Moon\n"
    "/forget — delete your data\n\n" + DISCLAIMER
)


def _fmt(lon: float) -> str:
    s = sign_index(lon)
    n, p = nakshatra(lon)
    d = lon % 30
    return f"{SIGNS[s]} ({RASHIS[s]}) {int(d)}°{int(d % 1 * 60):02d}' · {NAKSHATRAS[n]} p{p}"


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP)


async def birth(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args or []
    if len(args) < 3:
        await update.message.reply_text("Usage: /birth DD-MM-YYYY HH:MM City[, CC]")
        return
    try:
        local = datetime.strptime(f"{args[0]} {args[1]}", "%d-%m-%Y %H:%M")
    except ValueError:
        await update.message.reply_text("Couldn't read date/time. Use DD-MM-YYYY HH:MM (24h).")
        return
    place = find_place(" ".join(args[2:]))
    if not place:
        await update.message.reply_text("Place not found. Try a nearby larger city, or add a country code: Pune, IN")
        return
    utc = local_to_utc(local, place.tz)
    db.save_user(db.User(update.effective_chat.id, utc, place.latitude, place.longitude, place.tz,
                         f"{place.name}, {place.country}"))
    await update.message.reply_text(
        f"Saved: {local:%d %b %Y %H:%M} in {place.name}, {place.country} ({place.tz}) = {utc:%Y-%m-%d %H:%M} UTC.\n"
        "Wrong city? Send /birth again with a country code. Now try /chart."
    )


async def _user_or_prompt(update: Update) -> db.User | None:
    user = db.get_user(update.effective_chat.id)
    if not user:
        await update.message.reply_text("First tell me your birth details: /birth DD-MM-YYYY HH:MM City")
    return user


async def chart(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _user_or_prompt(update)
    if not user:
        return
    c = compute_chart(user.birth_utc, user.latitude, user.longitude)
    lagna = sign_index(c.ascendant)
    lines = [f"Lagna: {_fmt(c.ascendant)}", ""]
    for g in GRAHAS:
        pl = c.planets[g]
        h = house_from(lagna, sign_index(pl.longitude))
        lines.append(f"{g.title():8} H{h:<2} {_fmt(pl.longitude)}{' ℞' if pl.retrograde and g not in ('rahu', 'ketu') else ''}")
    yogas = fired(c, RULES)
    lines += ["", "Yogas:" if yogas else "No yogas from the current rule set."]
    lines += [f"• {r.name} — {r.effect} [{r.source['text']}]" for r in yogas]
    lines += ["", f"Ayanamsa (Lahiri): {c.ayanamsa:.4f}°", DISCLAIMER]
    await update.message.reply_text("\n".join(lines))


async def dasha(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _user_or_prompt(update)
    if not user:
        return
    c = compute_chart(user.birth_utc, user.latitude, user.longitude)
    cur = current_dasha(c.planets["moon"].longitude, user.birth_utc, datetime.now(timezone.utc))
    if not cur:
        await update.message.reply_text("Outside the 120-year Vimshottari cycle.")
        return
    maha, antar = cur
    await update.message.reply_text(
        f"Mahadasha: {maha.lord.title()} ({maha.start:%b %Y} → {maha.end:%b %Y})\n"
        f"Antardasha: {antar.lord.title()} ({antar.start:%d %b %Y} → {antar.end:%d %b %Y})"
    )


async def today(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _user_or_prompt(update)
    if not user:
        return
    natal = compute_chart(user.birth_utc, user.latitude, user.longitude)
    now = datetime.now(timezone.utc)
    sky = compute_chart(now, user.latitude, user.longitude)
    moon_sign = sign_index(natal.planets["moon"].longitude)
    facts = [f"Today the Moon is in {_fmt(sky.planets['moon'].longitude)}."]
    for g in ("moon", "jupiter", "saturn", "rahu"):
        h = house_from(moon_sign, sign_index(sky.planets[g].longitude))
        facts.append(f"Transiting {g.title()} is in house {h} from the natal Moon.")
    cur = current_dasha(natal.planets["moon"].longitude, user.birth_utc, now)
    if cur:
        facts.append(f"Running {cur[0].lord.title()} mahadasha, {cur[1].lord.title()} antardasha.")
    # TODO: gochara rules (rules/transits.yaml) to interpret the houses above.
    await update.message.reply_text(await narrate(facts) + "\n\n" + DISCLAIMER)


async def forget(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    db.delete_user(update.effective_chat.id)
    await update.message.reply_text("Your birth data has been deleted.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ["TELEGRAM_TOKEN"]
    app = Application.builder().token(token).build()
    for name, fn in [("start", start), ("help", start), ("birth", birth), ("chart", chart),
                     ("dasha", dasha), ("today", today), ("forget", forget)]:
        app.add_handler(CommandHandler(name, fn))
    log.info("samay starting (long polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
