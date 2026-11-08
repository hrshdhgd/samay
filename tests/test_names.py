import pytest

from samay.engine.names import fold, skeleton


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Forlì", "forli"),
        ("पुणे", "pune"),
        ("मुंबई", "mumbai"),
        ("औरंगाबाद", "aurangabad"),
        ("सोना", "sona"),
        ("  New-York!! ", "new york"),
        ("Łódź", "lodz"),
    ],
)
def test_fold(text, expected):
    assert fold(text) == expected


def test_fold_keeps_cyrillic():
    assert fold("Київ") == fold("КИЇВ")
    assert not fold("Київ").isascii()


@pytest.mark.parametrize(
    "variants",
    [
        ("Kolhapur", "Kolapur", "कोल्हापूर"),
        ("Nagpur", "Nagpoor", "नागपुर"),
        ("Pune", "Poona", "पुणे"),
        ("Kyiv", "Kiev"),
        ("Kharkiv", "Kharkov"),
        ("Calcutta", "Kolkata"),
    ],
)
def test_variants_share_a_skeleton(variants):
    assert len({skeleton(v) for v in variants}) == 1, [skeleton(v) for v in variants]


def test_different_cities_differ():
    assert skeleton("Pune") != skeleton("Nagpur")


def test_non_latin_has_no_skeleton():
    assert skeleton("Київ") == ""
