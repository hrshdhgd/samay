import sqlite3

import pytest

from samay import crypto
from samay.engine.errors import TooManyPeople
from samay.models import BirthInput
from samay.store import MAX_PEOPLE, MIGRATIONS, Store

MAYA = BirthInput("2015-03-14", "06:30", "Pune", "1259229", None, "parashari-lahiri", "Wagholi")
ARJUN = BirthInput("2018-11-02", "21:00", "Mumbai")


def dump(path) -> str:
    with sqlite3.connect(path) as c:
        return "\n".join(c.iterdump())


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db", crypto.generate_key())


def test_people_round_trip(store):
    a = store.save_person(1, "Maya", "daughter", MAYA)
    b = store.save_person(1, "Arjun", "son", ARJUN)
    people = store.list_people(1)
    assert [(p.id, p.name, p.relation) for p in people] == [
        (a, "Maya", "daughter"),
        (b, "Arjun", "son"),
    ]
    assert people[0].birth == MAYA and people[1].birth == ARJUN
    assert store.get_person(1, a).birth == MAYA


def test_nothing_about_a_person_is_readable_on_disk(store, tmp_path):
    store.save_person(1, "Maya", "daughter", MAYA)
    text = dump(tmp_path / "t.db")
    for word in (
        "Maya",
        "daughter",
        "2015-03-14",
        "06:30",
        "Pune",
        "1259229",
        "Wagholi",
    ):
        assert word not in text, word
    assert "parashari-lahiri" in text  # the profile name is not personal


def test_saving_the_same_name_again_updates_instead_of_duplicating(store):
    first = store.save_person(1, "Maya", "daughter", MAYA)
    again = store.save_person(1, "maya", "daughter", BirthInput("2015-03-14", "07:00", "Pune"))
    assert again == first and len(store.list_people(1)) == 1
    assert store.get_person(1, first).birth.time_text == "07:00"


def test_one_chat_cannot_see_or_delete_anothers_people(store):
    pid = store.save_person(1, "Maya", "daughter", MAYA)
    assert store.list_people(2) == [] and store.get_person(2, pid) is None
    assert store.delete_person(2, pid) is False and store.get_person(1, pid) is not None


def test_delete_one_person_leaves_the_others(store):
    a, b = store.save_person(1, "Maya", None, MAYA), store.save_person(1, "Arjun", None, ARJUN)
    assert store.delete_person(1, a) is True and [p.id for p in store.list_people(1)] == [b]
    assert store.delete_person(1, a) is False


def test_there_is_a_cap_per_chat_but_updates_still_work_at_the_cap(store):
    for i in range(MAX_PEOPLE):
        store.save_person(1, f"Person{i}", None, MAYA)
    with pytest.raises(TooManyPeople):
        store.save_person(1, "One too many", None, MAYA)
    store.save_person(1, "person3", None, ARJUN)  # an update, not a new row
    assert len(store.list_people(1)) == MAX_PEOPLE
    store.save_person(2, "Maya", None, MAYA)  # another chat has its own allowance


def test_forget_removes_all_of_a_chats_people_but_not_other_chats(store):
    store.save_person(1, "Maya", None, MAYA)
    keep = store.save_person(2, "Arjun", None, ARJUN)
    store.forget(1)
    assert store.list_people(1) == [] and [p.id for p in store.list_people(2)] == [keep]


def test_a_wrong_key_cannot_read_people(tmp_path):
    first = crypto.generate_key()
    Store(tmp_path / "t.db", first).save_person(1, "Maya", None, MAYA)
    with pytest.raises(crypto.StoreKeyError):
        Store(tmp_path / "t.db", crypto.generate_key())


def test_rekey_moves_people_too(tmp_path):
    old, new = crypto.generate_key(), crypto.generate_key()
    s = Store(tmp_path / "t.db", old)
    s.save_person(1, "Maya", "daughter", MAYA)
    s.rekey(new)
    assert Store(tmp_path / "t.db", new).list_people(1)[0].birth == MAYA and "Maya" not in dump(
        tmp_path / "t.db"
    )


def test_an_older_database_gains_the_people_table_in_place(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        for script in MIGRATIONS[:4]:
            c.executescript(script)
        c.execute("PRAGMA user_version = 4")
    s = Store(path, crypto.generate_key())
    s.save_person(1, "Maya", None, MAYA)
    assert s.list_people(1)[0].name == "Maya"
