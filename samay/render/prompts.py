"""Everything the bot says in conversation. Plain, short, warm; one question at a time."""
from __future__ import annotations

NAMASTE = "Namaste 🙏 Main Samay Hoon. I can show your Jyotish birth chart from your date, time and place of birth."

ASK_DATE = "When were you born?\nPlease type the date, for example 15-08-1952"
BAD_DATE = "I couldn't read that date. Please type it like this: 15-08-1952"
ASK_TIME = "Thank you. At what time were you born?\nFor example 6:30 am, or 18:30"
BAD_TIME = "I couldn't read that time. Please type it like this: 6:30 am"
ASK_AMPM = "Was that in the morning or in the evening?"
ASK_PLACE = "In which town or village were you born?\nYou can add the country, for example Pune, India"
ASK_NEARBY = (
    "I couldn't find “{place}”.\n"
    "Please type the nearest bigger town or city. The chart will say it is approximate."
)
ASK_NEARBY_AGAIN = "I couldn't find that either. Please try the district or the nearest large city."
PICK_PLACE = "I found more than one place. Which one is yours?"
PICK_FOLD = (
    "At that hour the clocks showed the same time twice that day (the clocks were turned back).\n"
    "Which one was it?"
)
NONEXISTENT = (
    "That time never happened on the clocks that day (the clocks were turned forward).\n"
    "Please tell me the time again."
)
SAVED = "Thank you. I have your birth details saved. Here is your chart:"
ASK_HOME = (
    "Which town or city do you live in now?\n"
    "I use it to work out sunrise and sunset for today's Rahu Kaala. For example: Maplewood, Minnesota"
)
HOME_NOT_FOUND = "I couldn't find that place. Please try the nearest bigger city, or add the country."
HOME_SAVED = "Thank you, I will use {place} for sunrise-based timings."
NEED_HOME = "To work out Rahu Kaala I need to know where you live now."
NO_SUNRISE = "The Sun does not both rise and set today in {place}, so there is no Rahu Kaala window."
BRIEF_ASK = "Every morning I can send a short message with today's date, Rahu Kaala and your running dasha.\nAt what time?"
BRIEF_ON = "Done. I will message you every morning at {time} ({place} time)."
BRIEF_OFF = "Done. No more morning messages."
BRIEF_STATUS_ON = "Your morning message is on, at {time} ({place} time)."
BRIEF_STATUS_OFF = "Your morning message is off."
BRIEF_NEED_HOME = "First, I need to know where you live now, so I can send the right time.\n\n"
STALE = "Sorry, that button is from an earlier conversation. Let's start again 🙏"
RE_ASK = "Please tap one of the buttons below."
UNKNOWN_TEXT = "I didn't understand that. Please use the menu below, or tap “My chart”."
NEED_BIRTH = "First I need your birth details."
CHANGED = "Your saved place is no longer unique, so please tell me your birth details again."
FORGET_ASK = "Shall I delete everything I know about you?"
FORGOTTEN = "Done. Everything has been deleted."
KEPT = "Okay, nothing was deleted."
GENERIC_ERROR = "Something went wrong. Please try again in a moment."

BTN_START_OVER = "↩ Start over"
BTN_START = "Start"
BTN_AM = "Morning (AM)"
BTN_PM = "Evening (PM)"
BTN_YES_DELETE = "Yes, delete"
BTN_NO = "No, keep"
BTN_BRIEF_OFF = "Turn off"

MENU_CHART = "🪐 My chart"
MENU_DASHA = "⏳ Dasha periods"
MENU_TODAY = "🌙 Today"
MENU_CHANGE = "✏️ Change birth details"
MENU_HOME = "📍 Where I live"
MENU_BRIEF = "🌅 Morning message"
MENU_FORGET = "🗑 Forget me"
MENU_ROWS = ((MENU_CHART, MENU_DASHA), (MENU_TODAY, MENU_CHANGE), (MENU_HOME, MENU_BRIEF), (MENU_FORGET,))

WELCOME = (
    NAMASTE + "\n\nUse the buttons at the bottom of the screen. "
    "The first time, I will ask for your birth details."
)

# Single source of truth for slash commands: the "/" menu in Telegram and /help are both built
# from this, in this order. Every command the bot registers must have an entry (tested).
COMMANDS = {
    "chart": "Your birth chart (kundali)",
    "dasha": "Your life chapters (dasha periods)",
    "today": "Today's sky and what is running now",
    "birth": "Enter or change your birth details",
    "home": "Tell me which city you live in now",
    "brief": "Daily morning message on or off",
    "help": "How to use samay",
    "forget": "Delete everything I know about you",
    "start": "Say namaste and show the menu",
}
HELP_ORDER = ("chart", "dasha", "today", "brief", "home", "birth", "forget")


def help_text() -> str:
    lines = [f"/{cmd} – {COMMANDS[cmd]}" for cmd in HELP_ORDER]
    return (
        "How to use samay 🙏\n\n"
        "Use the buttons at the bottom of the screen, or type a command:\n\n"
        + "\n".join(lines)
        + "\n\nFirst time? Tap “" + MENU_CHANGE + "” and I will ask three simple questions: "
        "your date, time and place of birth.\n\n"
        "If a button stops working, just send /start."
    )
