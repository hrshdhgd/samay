import io

import pytest
from PIL import Image

from samay import service
from samay.engine.paths import EPHEMERIS_PATH
from samay.models import BirthInput
from samay.render import chart_image as ci

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")


@pytest.fixture(scope="module")
def report():
    # Pune 1990-08-15 14:30: Scorpio lagna; Sun/Venus/Jupiter/Ketu Cancer, Moon Taurus, Mars Aries,
    # Mercury Leo, Saturn (retrograde) Sagittarius, Rahu Capricorn (checked against Swiss Ephemeris).
    return service.natal_report(service.resolve_birth(BirthInput("1990-08-15", "14:30", "Pune")))


def texts(marks):
    return [m.text for m in marks]


def test_planets_land_in_the_right_signs(report):
    by_sign = ci.marks_by_sign(report)
    assert texts(by_sign[3]) == ["Su", "Ve", "Ju", "Ke"]  # Cancer, in graha order
    assert texts(by_sign[1]) == ["Mo"] and texts(by_sign[0]) == ["Ma"] and texts(by_sign[4]) == ["Me"]
    assert texts(by_sign[8]) == ["Sa(R)"] and by_sign[8][0].retrograde
    assert texts(by_sign[9]) == ["Ra"] and not by_sign[9][0].retrograde  # nodes are not flagged
    assert sum(len(v) for v in by_sign.values()) == 9
    assert ci.lagna_sign(report) == 7  # Scorpio


def test_degrees_are_whole_degrees_within_the_sign(report):
    by_sign = ci.marks_by_sign(report, degrees=True)
    assert texts(by_sign[3]) == ["Su 28°", "Ve 8°", "Ju 5°", "Ke 12°"]
    assert texts(by_sign[8]) == ["Sa(R) 26°"]


def test_north_houses_count_from_the_lagna(report):
    houses = ci.north_houses(report)
    assert [n for n, _ in houses] == [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7]  # Scorpio is sign 8
    by_house = {i + 1: texts(m) for i, (_, m) in enumerate(houses)}
    assert by_house[2] == ["Sa(R)"] and by_house[3] == ["Ra"] and by_house[6] == ["Ma"]
    assert by_house[7] == ["Mo"] and by_house[9] == ["Su", "Ve", "Ju", "Ke"] and by_house[10] == ["Me"]
    assert by_house[1] == [] and by_house[4] == []


def test_south_grid_keeps_each_sign_in_its_fixed_box():
    cells = ci.SOUTH_CELLS
    assert len(set(cells.values())) == 12
    assert all(r in (0, 3) or c in (0, 3) for r, c in cells.values())  # only the outer ring is used
    assert (cells[11], cells[0], cells[1], cells[2]) == ((0, 0), (0, 1), (0, 2), (0, 3))  # Pisces..Gemini
    assert (cells[3], cells[4], cells[5]) == ((1, 3), (2, 3), (3, 3))  # Cancer, Leo, Virgo down the right
    assert (cells[6], cells[7], cells[8]) == ((3, 2), (3, 1), (3, 0))  # Libra..Sagittarius along the bottom
    assert (cells[9], cells[10]) == ((2, 0), (1, 0))  # Capricorn, Aquarius up the left


@pytest.mark.parametrize("style", ci.STYLES)
@pytest.mark.parametrize("degrees", [False, True])
def test_renders_a_png_of_the_expected_size(report, style, degrees):
    png = ci.render_chart_png(report, style, degrees)
    image = Image.open(io.BytesIO(png))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and image.format == "PNG"
    assert image.size == (ci.WIDTH, ci.HEIGHT) and len(png) < 400_000


def test_each_choice_changes_the_picture_and_rendering_is_deterministic(report):
    south, north = ci.render_chart_png(report, "south"), ci.render_chart_png(report, "north")
    assert south != north
    assert ci.render_chart_png(report, "south", True) != south
    assert ci.render_chart_png(report, "south") == south


def test_unknown_style_is_rejected(report):
    with pytest.raises(ValueError, match="style"):
        ci.render_chart_png(report, "round")


def test_a_crowded_house_still_fits_by_shrinking_the_type():
    pen = ci._Pen()
    nine = [ci.Mark(label, False) for label in ci.LABELS.values()]
    with_degrees = [ci.Mark(f"{label} 27°", False) for label in ci.LABELS.values()]
    for _, centre, w, h, _ in ci._north_cells(ci.MARGIN, ci.TOP, ci.SIDE):
        assert ci._draw_marks(pen, nine, centre, w, h)
    cell = ci.SIDE / 4
    assert ci._draw_marks(pen, nine, (300, 300), cell * 0.88, cell * 0.50)
    assert ci._draw_marks(pen, with_degrees, (300, 300), cell * 0.88, cell * 0.50)
    assert ci._draw_marks(pen, [], (0, 0), 10, 10)
