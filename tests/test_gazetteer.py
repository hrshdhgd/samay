import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from samay.engine import geo, paths
from samay.engine.errors import GazetteerMissing
from samay.engine.gazetteer_build import build
from samay.engine.names import fold

FIXTURES = Path(__file__).parent / "fixtures"
BIRTHPLACES = yaml.safe_load((FIXTURES / "birthplaces.yaml").read_text(encoding="utf-8"))
HIT_RATE = 0.95


def _hit(entry: dict) -> bool:
    want = entry["expect"]
    for p in geo.find_places(entry["query"]):
        if p.country == want["country"] and fold(p.name) == fold(want["name"]) and (
            "admin1" not in want or p.admin1 == want["admin1"]
        ):
            return True
    return False


def test_family_birthplaces_in_extract():
    assert all(_hit(e) for e in BIRTHPLACES)


def test_family_birthplaces_hit_rate_on_real_database(real_gazetteer):
    hits = sum(_hit(e) for e in BIRTHPLACES)
    assert hits / len(BIRTHPLACES) >= HIT_RATE, [e["query"] for e in BIRTHPLACES if not _hit(e)]


@pytest.mark.parametrize(
    "query,country,name",
    [
        ("Bombay", "IN", "Mumbai"),
        ("Kolapur", "IN", "Kolhapur"),
        ("Nagpoor", "IN", "Nagpur"),
        ("पुणे", "IN", "Pune"),
        ("कोल्हापूर", "IN", "Kolhapur"),
        ("Київ", "UA", "Kyiv"),
        ("Харьков", "UA", "Kharkiv"),
        ("Kharkov", "UA", "Kharkiv"),
        ("Forli", "IT", "Forlì"),
        ("Springfeld, IL", "US", "Springfield"),
    ],
)
def test_messy_spellings_find_the_place(query, country, name):
    first = geo.find_places(query)[0]
    assert (first.country, fold(first.name)) == (country, fold(name))


def test_village_only_in_country_file_found_in_devanagari():
    [village] = geo.find_places("शेंदूरजन")[:1]
    assert fold(village.name) == "shendurjan" and village.population == 0
    assert geo.find_places("Shendurjan, India")[0].id == village.id


def test_administrative_areas_hidden_when_a_city_matches():
    assert [p.label for p in geo.find_places("Mumbai")] == ["Mumbai, Maharashtra, IN"]
    assert [p.label for p in geo.find_places("Kiev, Ukraine")] == ["Kyiv, Kyiv City, UA"]


def test_administrative_area_offered_when_it_is_all_there_is():
    assert geo.find_places("Kyiv Oblast")[0].name == "Kyiv Oblast"


def test_qualifiers_narrow_by_code_name_and_country():
    assert [p.admin1 for p in geo.find_places("Maplewood, MN, USA")] == ["MN"]
    assert [p.admin1 for p in geo.find_places("Maplewood, Minnesota")] == ["MN"]
    assert [p.admin1_name for p in geo.find_places("Aurangabad, Maharashtra")] == ["Maharashtra"]
    assert geo.find_places("Maplewood, TX") == []


def test_labels_are_distinct_and_named_by_region():
    labels = [p.label for p in geo.find_places("Maplewood")]
    assert len(set(labels)) == len(labels) == 2
    assert labels[0] == "Maplewood, Ramsey County, Minnesota, US"


def test_nonsense_finds_nothing():
    assert geo.find_places("Nowhereville") == []
    assert geo.find_places("   ") == []


def test_kolapur_prefers_the_city_over_hamlets_spelled_that_way(real_gazetteer):
    first = geo.find_places("Kolapur")[0]
    assert fold(first.name) == "kolhapur" and first.population > 100_000


def test_real_database_matches_its_lock(real_gazetteer):
    lock = paths.GAZETTEER_PATH.with_name("gazetteer.lock")
    if not lock.exists():
        pytest.skip("no gazetteer.lock")
    digest = hashlib.sha256(paths.GAZETTEER_PATH.read_bytes()).hexdigest()
    assert digest == json.loads(lock.read_text())["database_sha256"]


def test_builder_output_shape_and_determinism(tmp_path):
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    for out in (a, b):
        build(FIXTURES / "geonames-mini", out, ["IN", "US", "UA", "IT"], snapshot="t", sources={"x": "1"})
    assert a.read_bytes() == b.read_bytes()
    conn = sqlite3.connect(a)
    assert dict(conn.execute("SELECT key, value FROM meta"))["snapshot"] == "t"
    extract = FIXTURES / "geonames-mini"
    ids = {
        line.split("\t")[0]
        for stem in ("cities500", "IN", "US", "UA", "IT")
        for line in (extract / f"{stem}.txt").read_text(encoding="utf-8").splitlines()
    }
    assert conn.execute("SELECT count(*) FROM places").fetchone()[0] == len(ids)
    assert conn.execute("SELECT count(*) FROM places WHERE fcode LIKE 'PCL%'").fetchone()[0] == 0
    assert conn.execute("SELECT name FROM countries WHERE iso3 = 'USA'").fetchone()[0] == "United States"


def test_missing_database_is_a_typed_error(tmp_path, fixture_gazetteer):
    geo.configure(tmp_path / "absent.sqlite")
    try:
        with pytest.raises(GazetteerMissing):
            geo.find_places("Pune")
    finally:
        geo.configure(fixture_gazetteer)
