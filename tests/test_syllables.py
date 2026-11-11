import pytest

from samay.engine import syllables
from samay.engine.vedic import NAK_SPAN, NAKSHATRAS


def test_the_table_has_every_pada_of_every_nakshatra():
    table = syllables.load_table()
    assert len(table) == 108
    assert {n for n, _ in table} == set(NAKSHATRAS) and {p for _, p in table} == {1, 2, 3, 4}
    assert all(s.syllable and s.devanagari for s in table.values())


@pytest.mark.parametrize(
    "longitude,nakshatra,pada,syllable",
    [(0.0, "Ashwini", 1, "Chu"), (3.4, "Ashwini", 2, "Che"), (NAK_SPAN + 0.1, "Bharani", 1, "Li"),
     (359.9, "Revati", 4, "Chi"), (NAK_SPAN * 3 + 0.1, "Rohini", 1, "O"), (NAK_SPAN * 21 + 0.1, "Shravana", 1, "Khi")],
)
def test_the_syllable_follows_the_moons_nakshatra_and_pada(longitude, nakshatra, pada, syllable):
    s = syllables.naming_syllable(longitude)
    assert (s.nakshatra, s.pada, s.syllable) == (nakshatra, pada, syllable)


def test_readings_used_by_other_traditions_are_kept_and_shown():
    shravana = syllables.naming_syllable(NAK_SPAN * 21 + 0.1)
    assert shravana.also == ("Ju",) and "other traditions also use Ju" in str(shravana)
    assert syllables.naming_syllable(0.0).also == () and str(syllables.naming_syllable(0.0)) == "Chu"


def test_the_syllables_follow_the_known_sequence_of_the_avakahada_chakra():
    seq = [s.syllable for n in NAKSHATRAS for s in (syllables.load_table()[(n, p)] for p in (1, 2, 3, 4))]
    assert seq[:8] == ["Chu", "Che", "Cho", "La", "Li", "Lu", "Le", "Lo"]
    assert seq[-8:] == ["Du", "Tha", "Jha", "Yna", "De", "Do", "Cha", "Chi"]


def test_jyeshtha_pada_one_is_the_text_no_and_not_the_boolean_false():
    s = syllables.load_table()[("Jyeshtha", 1)]
    assert s.syllable == "No" and s.devanagari == "नो"


def test_a_syllable_that_yaml_reads_as_a_boolean_is_rejected(tmp_path):
    rows = "\n".join(f"- nakshatra: {n}\n  padas: [{{syllable: Chu, devanagari: x}}, {{syllable: Che, devanagari: x}}, "
                     f"{{syllable: Cho, devanagari: x}}, {{syllable: No, devanagari: x}}]" for n in NAKSHATRAS)
    bad = tmp_path / "t.yaml"
    bad.write_text(rows + "\n")
    with pytest.raises(TypeError, match="must be quoted text"):
        syllables.load_table(bad)


def test_a_malformed_table_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text("- {nakshatra: Ashwini, padas: [{syllable: Chu, devanagari: x}]}\n")
    with pytest.raises(ValueError, match="27 nakshatras"):
        syllables.load_table(bad)
