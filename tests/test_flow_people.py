import json

from samay.bot import flow
from samay.engine import geo
from samay.models import BirthInput
from samay.narrative import Extraction, Mentioned
from samay.render import prompts

MAYA = Mentioned("Maya", "daughter", "2015-03-14", "06:30", None, "Pune, India")
ARJUN = Mentioned(
    "Arjun", "son", "", "", (9, 0), "Mumbai"
)  # no date; "9" with no am/pm


def labels(o):
    return [b.label for row in o.reply.buttons for b in row]


def tap(o, label):
    for row in o.reply.buttons:
        for b in row:
            if b.label == label:
                return flow.on_button(o.draft, b.data)
    raise AssertionError(f"no button {label!r} in {labels(o)}")


def say(o, *texts):
    for t in texts:
        o = flow.on_text(o.draft, t)
    return o


def test_asking_step_by_step_names_the_person_in_every_question():
    o = flow.begin_person(narrate=False)
    assert o.reply.text == prompts.ASK_NAME and o.draft.purpose == "person"
    o = say(o, "Maya")
    assert o.draft.step == "relation" and labels(o)[:7] == [
        "Daughter",
        "Son",
        "Wife",
        "Husband",
        "Mother",
        "Father",
        "Friend",
    ]
    o = tap(o, "Daughter")
    assert (
        o.reply.text
        == "When was Maya born?\nPlease type the date, for example 15-08-2012"
    )
    o = say(o, "14-03-2015")
    assert o.reply.text.startswith("At what time was Maya born?")
    o = tap(say(o, "6:30"), prompts.BTN_AM)
    assert o.reply.text.startswith("In which town or village was Maya born?")
    o = say(o, "Pune, India")
    assert o.draft.step == "person_confirm"
    assert (
        "👤 Maya (daughter)" in o.reply.text
        and "Born 14 Mar 2015, 6:30 am" in o.reply.text
        and "Pune" in o.reply.text
    )
    assert labels(o)[:3] == [
        "💾 Yes, save Maya",
        "Yes, just for now",
        "✏️ Fix something",
    ]
    done = tap(o, "💾 Yes, save Maya")
    assert (
        done.draft is None and done.done is None and done.then is None
    )  # not the user's own details
    assert done.person == flow.PersonResult(
        "Maya",
        "daughter",
        BirthInput(
            "2015-03-14",
            "06:30",
            "Pune, India",
            geo.find_places("Pune, India")[0].id,
            None,
            "parashari-lahiri",
            None,
        ),
        True,
    )
    assert done.reply.text == prompts.PERSON_DONE.format(name="Maya")


def test_just_for_now_confirms_without_saving():
    o = tap(say(flow.begin_person(False), "Maya"), "Skip")
    o = say(o, "14-03-2015", "18:30", "Pune")
    assert tap(o, prompts.BTN_KEEP_PERSON).person.save is False


def test_a_free_text_relation_is_cleaned_and_skipping_it_is_fine():
    o = say(say(flow.begin_person(False), "Maya"), "  Niece \n")
    assert o.draft.relation == "niece" and o.draft.step == "date"
    assert tap(say(flow.begin_person(False), "Maya"), "Skip").draft.relation == ""


def test_a_blank_name_is_asked_again():
    o = say(flow.begin_person(False), "   ")
    assert o.draft.step == "name" and o.reply.text == prompts.ASK_NAME


def test_two_children_in_one_message_are_checked_one_after_the_other_and_the_question_waits():
    ext = Extraction((MAYA, ARJUN), "What will their future be like?", "")
    o = flow.from_extraction(ext)
    assert (
        o.draft.step == "person_confirm"
        and "After this I'll check the details for Arjun." in o.reply.text
    )
    o = tap(o, prompts.BTN_KEEP_PERSON)  # Maya, just for now
    assert (
        o.person.name == "Maya" and not o.person.save and o.then is None
    )  # the question waits for Arjun
    assert (
        o.reply.text.startswith("Thank you, that's Maya done.")
        and "When was Arjun born?" in o.reply.text
    )
    o = say(o, "2 Nov 2018")
    assert (
        o.draft.step == "ampm"
    )  # his time was "9", so morning or evening is still asked
    o = tap(o, prompts.BTN_PM)
    assert (
        o.draft.step == "person_confirm"
        and "Born 02 Nov 2018, 9:00 pm" in o.reply.text
        and "Mumbai" in o.reply.text
    )
    done = tap(o, "💾 Yes, save Arjun")
    assert (
        done.person.name == "Arjun"
        and done.person.save
        and done.person.birth.time_text == "21:00"
    )
    assert done.then == ("What will their future be like?", "") and done.draft is None


def test_only_what_is_missing_is_asked():
    complete_but_for_a_name = Mentioned(
        "", "", "2015-03-14", "06:30", None, "Pune, India"
    )
    o = flow.from_extraction(Extraction((complete_but_for_a_name,)))
    assert o.draft.step == "name"
    assert (
        say(o, "Maya").draft.step == "person_confirm"
    )  # the relation is not asked of a narrative's people
    only_place_missing = flow.from_extraction(
        Extraction((Mentioned("Maya", "", "2015-03-14", "06:30", None, ""),))
    )
    assert (
        only_place_missing.draft.step == "place"
        and "When was" not in only_place_missing.reply.text
    )


def test_a_place_the_model_read_that_is_unknown_asks_for_the_nearest_town_and_marks_it_approximate():
    o = flow.from_extraction(
        Extraction(
            (Mentioned("Maya", "", "2015-03-14", "06:30", None, "Nowhereville"),)
        )
    )
    assert o.draft.step == "nearby" and "Nowhereville" in o.reply.text
    o = say(o, "Pune")
    assert (
        o.draft.step == "person_confirm"
        and "(the nearest town to “Nowhereville”)" in o.reply.text
    )
    assert tap(o, prompts.BTN_KEEP_PERSON).person.birth.approx_for == "Nowhereville"


def test_an_ambiguous_place_offers_labelled_buttons_in_the_persons_name():
    o = flow.from_extraction(
        Extraction((Mentioned("Maya", "", "2015-03-14", "06:30", None, "Maplewood"),))
    )
    assert (
        o.draft.step == "pick_place"
        and o.reply.text == "I found more than one place. Which one was Maya born in?"
    )
    o = tap(o, "Maplewood, Essex County, New Jersey, US")
    assert o.draft.step == "person_confirm" and "Maplewood" in o.reply.text


def test_a_repeated_clock_time_and_a_time_that_never_happened_are_handled_for_a_person_too():
    repeated = flow.from_extraction(
        Extraction(
            (Mentioned("Maya", "", "2021-11-07", "01:30", None, "New York City"),)
        )
    )
    assert repeated.draft.step == "pick_fold"
    assert tap(repeated, labels(repeated)[1]).draft.step == "person_confirm"
    skipped = flow.from_extraction(
        Extraction(
            (Mentioned("Maya", "", "2021-03-14", "02:30", None, "New York City"),)
        )
    )
    assert skipped.draft.step == "time" and skipped.reply.text.startswith(
        prompts.NONEXISTENT
    )
    assert "At what time was Maya born?" in skipped.reply.text
    assert (
        say(skipped, "3:30 am").draft.step == "person_confirm"
    )  # the place is not asked again


def test_fix_something_keeps_the_person_but_asks_the_details_again():
    o = flow.from_extraction(Extraction((MAYA,)))
    o = tap(o, prompts.BTN_FIX)
    assert (
        o.draft.step == "date"
        and o.draft.name == "Maya"
        and o.reply.text.startswith("When was Maya born?")
    )
    assert (
        o.draft.date_text == ""
        and o.draft.time_text == ""
        and o.draft.place_choice is None
    )
    o = say(o, "15-03-2015", "7:00 am", "Pune")
    assert "Born 15 Mar 2015, 7:00 am" in o.reply.text


def test_a_tap_from_an_old_message_never_saves_anyone():
    o = flow.from_extraction(Extraction((MAYA,)))
    old = o.reply.buttons[0][0].data
    newer = tap(o, prompts.BTN_FIX)
    result = flow.on_button(newer.draft, old)
    assert result.reply.text == prompts.STALE and result.person is None
    assert flow.on_button(None, old).person is None


def test_a_draft_survives_a_restart_in_the_middle_of_several_people():
    o = flow.from_extraction(
        Extraction(
            (MAYA, ARJUN, Mentioned("Ria", "", "2020-01-05", "08:00", None, "Pune")),
            "q?",
            "Maya",
        )
    )
    restored = flow.Draft.from_dict(json.loads(json.dumps(o.draft.to_dict())))
    assert (
        restored == o.draft
        and len(restored.queue) == 2
        and restored.question == "q?"
        and restored.about == "Maya"
    )
    again = flow.on_button(
        restored, o.reply.buttons[1][0].data
    )  # the old keyboard still works after the restart
    assert again.person.name == "Maya" and again.draft.name == "Arjun"


def test_start_over_restarts_the_right_conversation():
    mid_person = say(flow.begin_person(False), "Maya")
    assert flow.on_button(mid_person.draft, flow.START_OVER).draft.purpose == "person"
    assert flow.on_button(mid_person.draft, flow.START_OVER).draft.step == "name"
    narrated = flow.begin_person(True)
    assert flow.on_button(narrated.draft, flow.START_OVER).draft.step == "narrate"
    assert (
        flow.on_button(flow.begin_home().draft, flow.START_OVER).draft.purpose == "home"
    )
    assert flow.on_button(flow.begin().draft, flow.START_OVER).draft.purpose == "birth"


def test_the_narrative_step_invites_a_story_and_can_fall_back_to_steps():
    o = flow.begin_person(True)
    assert (
        o.draft.step == "narrate"
        and o.reply.text == prompts.ASK_NARRATE
        and prompts.BTN_GUIDED in labels(o)
    )
    fallback = flow.on_text(
        o.draft, "she was born in the morning"
    )  # the model could not read it
    assert fallback.draft.step == "name" and fallback.reply.text.startswith(
        prompts.NARRATE_FAILED
    )
    guided = tap(o, prompts.BTN_GUIDED)
    assert guided.draft.step == "name" and guided.draft.narrate is False


def test_asking_about_someone_never_changes_the_users_own_flow():
    assert say(flow.begin(), "15-08-1952", "18:30", "Pune, India").done is not None
    person = flow.from_extraction(Extraction((MAYA,)))
    assert person.done is None and person.home is None
