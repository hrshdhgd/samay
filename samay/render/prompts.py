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

# ---- asking about someone else (a child, a spouse, a parent) ----
ASK_NARRATE = (
    "Tell me about them in your own words: their name, and the date, time and place of birth. "
    "You can describe more than one person in the same message."
)
NARRATE_FAILED = "I couldn't make that out, so let's do it step by step."
ASK_NAME = "What is their name? A first name is enough."
ASK_RELATION = "How are they related to you?"
BTN_REL_SKIP = "Skip"
ASK_DATE_FOR = "When was {name} born?\nPlease type the date, for example 15-08-2012"
ASK_TIME_FOR = "At what time was {name} born?\nFor example 6:30 am, or 18:30"
ASK_PLACE_FOR = "In which town or village was {name} born?\nYou can add the country, for example Pune, India"
PICK_PLACE_FOR = "I found more than one place. Which one was {name} born in?"
CONFIRM_PERSON = "Here is what I understood:\n\n👤 {name}{rel}\nBorn {date}, {time}\n📍 {place}{more}\n\nIs that right?"
CONFIRM_MORE = "\n\nAfter this I'll check the details for {names}."
BTN_SAVE_PERSON = "💾 Yes, save {name}"
BTN_KEEP_PERSON = "Yes, just for now"
BTN_FIX = "✏️ Fix something"
BTN_GUIDED = "Step by step instead"
PERSON_NEXT = "Thank you, that's {name} done."
PERSON_DONE = "Thank you. We are now talking about {name}."
PEOPLE_TITLE = "People I can talk about"
PEOPLE_EMPTY = "I don't know anyone else yet. Tap “➕ Add someone” and tell me about them."
PEOPLE_NOW = "Right now we are talking about {name}."
PEOPLE_NOW_SELF = "Right now we are talking about you."
BTN_ADD_PERSON = "➕ Add someone"
BTN_ABOUT_ME = "👤 Me"
BTN_DELETE_PERSON = "🗑 Delete {name}"
BTN_REALLY_DELETE = "Yes, delete {name}"
ASK_DELETE_PERSON = "Delete {name} and their birth details?"
PERSON_DELETED = "Done. {name} has been deleted."
PERSON_UNRESOLVED = "I couldn't work out {name}'s chart from the details I have. Please open /people, delete them and add them again."
PEOPLE_SAVED_LIST = "Saved: {names}. You can find them under /people."
PERSON_GONE = "I can't find that person any more."
PERSON_SAVED_NOTE = "Saved. You can find {name} under /people."
PEOPLE_FULL = "I can keep up to {limit} people. Please delete one first."
SWITCHED = "👤 Now talking about {name}."
SWITCHED_SELF = "👤 Now talking about you."
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
ASK_QUESTION = (
    "What would you like to know? Ask about a planet, a house or a dasha, for example:\n"
    "• What does Saturn stand for?\n• What does the 4th house mean?\n• What is my future?"
)
NO_TOPIC = (
    "I can only answer from classical texts that have been checked, and from your own chart. "
    "I don't predict events.\n\n"
    "Try asking about a planet or a dasha, for example: “What does Saturn stand for?”"
)
READING_FRAME = (
    "This is what a 6th-century text says. It is not a forecast, and many of its lines will not "
    "fit a modern life."
)
NO_SOURCE = (
    "I don't have a checked source for this yet, so I won't guess. "
    "I have noted the topic so it can be researched."
)
NEED_BIRTH_FOR_FACTS = "Tell me your birth details (“✏️ Change birth details”) and I can add facts from your own chart."
VERSE_UNPROOFREAD = (
    "ⓘ Verse text: a typed copy from sanskritdocuments.org, compared with the GRETIL copy. No Sanskrit reader "
    "has proofread it, so a typing slip is possible."
)
BTN_SANSKRIT = "📜 Show Sanskrit"
BTN_ENGLISH = "🔤 English"
DASHA_FRAME = (
    "An old text's general list, not a forecast. How much applies depends on how strong and well placed the planet "
    "is in the chart."
)
READING_FRAME_SHORT = "An old text's view, not a forecast."
FUTURE_TITLE = "🔮 {Your} current period of life"
NEED_BIRTH_FOR_FUTURE = (
    "To look at your future I need your birth details first. Tap “✏️ Change birth details”, then ask me again."
)
BTN_MORE = "➕ More"
BTN_LESS = "➖ Less"
LIFE_FRAME = (
    "This shows what the text associates with this area and what sits there in {your} chart. It cannot say whether or "
    "when anything will happen."
)
OUTLOOK_KEY = "Houses are counted from the Moon sign. ✓ marks a house the text counts as good for that planet."
OUTLOOK_FRAME = "What an old text says about these transits and sub-chapters, not a forecast."
OUTLOOK_NOT_APPLIED = (
    "The text adds refinements this reading does not apply yet: aspects from good and bad planets, each planet's "
    "strength in the sign, and the part of the sign where it acts. It also says a sign with many points can turn a hard "
    "house good; the points are shown, but they do not change the verdict above. Ketu has no results in the text."
)
OUTLOOK_ASHTAKA_NOTE = (
    "Points (ashtakavarga) are a planet's benefic points in the sign it is passing, counted from your birth chart with "
    "Phaladeepika's tables. Brihat Jataka's tables differ from them in {n} of the 56 lists."
)
OUTLOOK_DASHA_UNCHECKED = "What the text says about each sub-chapter is waiting for a check, so it is not shown yet."
OUTLOOK_UNCHECKED = (
    "The text's results for these transits are waiting for a check, so for now I show only where the planets are."
)
NEED_BIRTH_FOR_CHART = "To count your ashtakavarga I need your birth details first. Tap “✏️ Change birth details”, then ask me again."
ASHTAKA_UNCHECKED = (
    "I count the points for your chart, but the tables are waiting for a check against the book, so I don't show "
    "the numbers yet."
)
ASHTAKA_KEY = "Points are the benefic dots the seven planets and the lagna give each sign; ✓ marks a sign above the text's 28."
NEED_BIRTH_FOR_MOON = "To read your Moon I need your birth details first. Tap “✏️ Change birth details”, then ask me again."
MOON_UNCHECKED = (
    "I know where your Moon is, but the text's descriptions of it are waiting for a check against the book, so I don't "
    "show them yet."
)
MOON_YOGAS_UNCHECKED = "What the text says about the yogas the Moon makes is waiting for a check, so it is not shown yet."
LORDSHIP_UNDECIDED = "The text sets conditions for strong and weak; this chart meets neither set, so both readings are given."
MINOR_NOTE = "ⓘ The classical texts describe adult life, so for a child this is only a general reading."
NO_TOPIC_AI = "I have no checked source for this."
NO_SOURCE_AI = "I don't have a checked source for this yet. I have noted the topic so it can be researched."
AI_CAVEAT = "This is a small AI model's own answer from general knowledge, not from a checked source, and it may be wrong."
AI_UNAVAILABLE = "🤖 The AI could not answer just now. The sourced answer above is all I have."
STALE = "Sorry, that button is from an earlier conversation. Let's start again 🙏"
RE_ASK = "Please tap one of the buttons below."
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
MENU_ASK = "❓ Ask a question"
MENU_PEOPLE = "👥 People"
MENU_ROWS = ((MENU_ASK, MENU_PEOPLE), (MENU_CHART, MENU_DASHA), (MENU_TODAY, MENU_CHANGE), (MENU_HOME, MENU_BRIEF), (MENU_FORGET,))

WELCOME = (
    NAMASTE + "\n\nUse the buttons at the bottom of the screen. "
    "The first time, I will ask for your birth details."
)

# Single source of truth for slash commands: the "/" menu in Telegram and /help are both built
# from this, in this order. Every command the bot registers must have an entry (tested).
COMMANDS = {
    "ask": "Ask about a planet, a house or a dasha",
    "people": "Add or choose someone to ask about",
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
HELP_ORDER = ("ask", "people", "chart", "dasha", "today", "brief", "home", "birth", "forget")


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
