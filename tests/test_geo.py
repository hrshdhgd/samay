from samay.engine.geo import find_places, get_place


def test_pune_resolves():
    [p] = find_places("Pune, IN")
    assert p.tz == "Asia/Kolkata" and p.country == "IN"
    assert get_place(p.id) == p


def test_duplicates_ranked_by_population_in_different_regions():
    places = find_places("Springfield, US")
    assert len(places) == 3
    assert len({p.admin1 for p in places}) == 3
    assert [p.population for p in places] == sorted((p.population for p in places), reverse=True)


def test_country_filter():
    assert {p.country for p in find_places("London")} == {"GB", "CA"}
    assert [p.country for p in find_places("London, CA")] == ["CA"]


def test_unknown_place():
    assert find_places("Nowhereville") == []
