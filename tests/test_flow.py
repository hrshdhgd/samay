from samay.bot import flow
from samay.render import prompts


def labels(outcome):
    return [b.label for row in outcome.reply.buttons for b in row]


def tap(outcome, label):
    """Press the button with this label on the latest reply."""
    for row in outcome.reply.buttons:
        for b in row:
            if b.label == label:
                return flow.on_button(outcome.draft, b.data)
    raise AssertionError(f"no button {label!r} in {labels(outcome)}")


def say(outcome, *texts):
    for t in texts:
        outcome = flow.on_text(outcome.draft, t)
    return outcome


def test_happy_path_collects_everything_and_asks_one_thing_at_a_time():
    o = flow.begin()
    assert o.reply.text == prompts.ASK_DATE and labels(o) == [prompts.BTN_START_OVER]
    o = flow.on_text(o.draft, "15th August 1952")
    assert o.reply.text == prompts.ASK_TIME and o.draft.date_text == "1952-08-15"
    o = flow.on_text(o.draft, "18:30")
    assert o.reply.text == prompts.ASK_PLACE and o.draft.time_text == "18:30"
    o = flow.on_text(o.draft, "Pune, India")
    assert o.draft is None and o.reply.text == prompts.SAVED
    assert (o.done.date_text, o.done.time_text, o.done.place_text) == ("1952-08-15", "18:30", "Pune, India")
    assert o.done.place_choice and not o.done.approx_for


def test_time_without_am_pm_asks_morning_or_evening():
    o = say(flow.begin(), "15-08-1952", "6:30")
    assert o.draft.step == "ampm" and labels(o) == [prompts.BTN_AM, prompts.BTN_PM, prompts.BTN_START_OVER]
    assert tap(o, prompts.BTN_PM).draft.time_text == "18:30"
    assert tap(o, prompts.BTN_AM).draft.time_text == "06:30"


def test_twelve_oclock_am_is_midnight_and_pm_is_noon():
    o = say(flow.begin(), "15-08-1952", "12:10")
    assert tap(o, prompts.BTN_AM).draft.time_text == "00:10"
    assert tap(o, prompts.BTN_PM).draft.time_text == "12:10"


def test_bad_date_and_time_reask_the_same_question():
    o = say(flow.begin(), "yesterday")
    assert o.reply.text == prompts.BAD_DATE and o.draft.step == "date"
    o = say(o, "15-08-1952", "half past six")
    assert o.reply.text == prompts.BAD_TIME and o.draft.step == "time"


def test_duplicate_place_names_become_labelled_buttons():
    o = say(flow.begin(), "15-08-1952", "18:30", "Maplewood")
    assert o.draft.step == "pick_place"
    assert labels(o)[:2] == ["Maplewood, Ramsey County, Minnesota, US", "Maplewood, Essex County, New Jersey, US"]
    done = tap(o, "Maplewood, Essex County, New Jersey, US")
    assert done.done.place_choice and done.draft is None


def test_unknown_place_asks_for_nearest_town_and_marks_the_chart_approximate():
    o = say(flow.begin(), "15-08-1952", "18:30", "Nowhereville")
    assert o.draft.step == "nearby" and "Nowhereville" in o.reply.text
    o = say(o, "Atlantis")
    assert o.draft.step == "nearby" and o.reply.text.startswith(prompts.ASK_NEARBY_AGAIN)
    o = say(o, "Pune")
    assert o.done.approx_for == "Nowhereville" and o.done.place_text == "Pune"


def test_repeated_clock_time_asks_which_one():
    o = say(flow.begin(), "07-11-2021", "1:30 am", "New York City")
    assert o.draft.step == "pick_fold"
    assert labels(o)[0].startswith("first occurrence")
    done = tap(o, labels(o)[1])
    assert done.done.fold == 1


def test_time_that_never_happened_returns_to_the_time_question():
    o = say(flow.begin(), "14-03-2021", "2:30 am", "New York City")
    assert o.draft.step == "time" and o.reply.text.startswith(prompts.NONEXISTENT)
    o = say(o, "3:30 am", "New York City")
    assert o.done is not None


def test_stale_tap_gets_a_friendly_restart_button():
    o = say(flow.begin(), "15-08-1952", "6:30")
    old = o.reply.buttons[0][0].data
    newer = tap(o, prompts.BTN_PM)
    result = flow.on_button(newer.draft, old)  # the old message's button, after the draft moved on
    assert result.reply.text == prompts.STALE and result.draft == newer.draft
    assert result.reply.buttons[0][0].data == flow.START_OVER
    assert flow.on_button(None, old).reply.text == prompts.STALE


def test_text_where_a_button_is_expected_reasks_with_the_buttons():
    o = say(flow.begin(), "15-08-1952", "6:30", "morning")
    assert o.draft.step == "ampm" and o.reply.text.startswith(prompts.RE_ASK)
    assert prompts.BTN_AM in labels(o)
    before = say(flow.begin(), "15-08-1952", "6:30")
    after = flow.on_text(before.draft, "evening")
    assert after.draft.token == before.draft.token  # old buttons stay valid


def test_start_over_works_from_any_step_and_without_a_draft():
    o = say(flow.begin(), "15-08-1952", "18:30")
    again = flow.on_button(o.draft, flow.START_OVER)
    assert again.draft.step == "date" and again.reply.text == prompts.ASK_DATE
    assert flow.on_button(None, flow.START_OVER).draft.step == "date"


def test_draft_survives_a_json_round_trip():
    o = say(flow.begin(), "15-08-1952", "6:30")
    restored = flow.Draft.from_dict(o.draft.to_dict())
    assert restored == o.draft
    assert tap(o, prompts.BTN_PM).draft.time_text == flow.on_button(restored, o.reply.buttons[0][1].data).draft.time_text


def test_free_text_with_no_draft_starts_the_conversation():
    assert flow.on_text(None, "hello").reply.text == prompts.ASK_DATE
