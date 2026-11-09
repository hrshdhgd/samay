"""Birth-chart pictures in South and North Indian style, drawn offline with Pillow.

Layout (which planet sits in which box) is plain data from `marks_by_sign` / `north_houses`, so
it is tested exactly; the drawing code only places that data on the canvas. The Jataka PDF can
reuse both. Only glyphs of Pillow's bundled font are used, so retrograde is marked "(R)".
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from ..engine.ephemeris import GRAHAS
from ..engine.vedic import SIGNS, sign_index
from ..models import NatalReport

STYLES = ("south", "north")
LABELS = {
    "sun": "Su", "moon": "Mo", "mars": "Ma", "mercury": "Me", "jupiter": "Ju",
    "venus": "Ve", "saturn": "Sa", "rahu": "Ra", "ketu": "Ke",
}
LEGEND = (
    "Su Sun   Mo Moon   Ma Mars   Me Mercury   Ju Jupiter",
    "Ve Venus   Sa Saturn   Ra Rahu   Ke Ketu   (R) moving backwards",
)

# South Indian: signs stay in fixed boxes (Pisces top-left, clockwise); only the lagna mark moves.
SOUTH_CELLS = {
    11: (0, 0), 0: (0, 1), 1: (0, 2), 2: (0, 3),
    3: (1, 3), 4: (2, 3), 5: (3, 3),
    6: (3, 2), 7: (3, 1), 8: (3, 0),
    9: (2, 0), 10: (1, 0),
}

WIDTH, HEIGHT, MARGIN = 1080, 1290, 40
SIDE = WIDTH - 2 * MARGIN  # the square chart
TOP = 160
SUPERSAMPLE = 2  # drawn at 2x and scaled down, for smooth lines
LINE_HEIGHT = 1.25

NAVY, PANEL = (11, 18, 38), (24, 36, 70)
GOLD, GOLD_DIM = (212, 175, 55), (150, 128, 60)
WHITE, RETRO = (240, 240, 245), (255, 150, 130)


@dataclass(frozen=True)
class Mark:
    text: str  # "Sa", "Sa(R)", or "Sa 26°" when degrees are shown
    retrograde: bool


def _mark(name: str, longitude: float, retrograde: bool, degrees: bool) -> Mark:
    text = LABELS[name] + ("(R)" if retrograde and name not in ("rahu", "ketu") else "")
    if degrees:
        text += f" {int(longitude % 30)}°"
    return Mark(text, retrograde and name not in ("rahu", "ketu"))


def marks_by_sign(report: NatalReport, degrees: bool = False) -> dict[int, list[Mark]]:
    """Sign index (0-11) -> planet marks in that sign, in the usual graha order."""
    out: dict[int, list[Mark]] = {i: [] for i in range(12)}
    for g in GRAHAS:
        p = report.chart.planets[g]
        out[sign_index(p.longitude)].append(_mark(g, p.longitude, p.retrograde, degrees))
    return out


def lagna_sign(report: NatalReport) -> int:
    return sign_index(report.chart.ascendant)


def north_houses(report: NatalReport, degrees: bool = False) -> list[tuple[int, list[Mark]]]:
    """House 1-12 as (sign number 1-12, marks). House 1 is the lagna sign."""
    by_sign, lagna = marks_by_sign(report, degrees), lagna_sign(report)
    return [((lagna + h) % 12 + 1, by_sign[(lagna + h) % 12]) for h in range(12)]


# --- drawing ---------------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=px)


class _Pen:
    """Draws in design units (1080 wide) onto a supersampled canvas."""

    def __init__(self) -> None:
        self.image = Image.new("RGB", (WIDTH * SUPERSAMPLE, HEIGHT * SUPERSAMPLE), NAVY)
        self.draw = ImageDraw.Draw(self.image)

    @staticmethod
    def _pts(points):
        return [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in points]

    def line(self, points, fill=GOLD, width=3):
        self.draw.line(self._pts(points), fill=fill, width=round(width * SUPERSAMPLE), joint="curve")

    def polygon(self, points, fill=None, outline=None, width=3):
        self.draw.polygon(self._pts(points), fill=fill, outline=outline, width=round(width * SUPERSAMPLE))

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=3):
        self.polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, outline, width)

    def text(self, xy, s, px, fill=WHITE, anchor="mm", bold=False):
        x, y = xy
        self.draw.text((x * SUPERSAMPLE, y * SUPERSAMPLE), s, font=_font(px * SUPERSAMPLE), fill=fill,
                       anchor=anchor, stroke_width=SUPERSAMPLE if bold else 0, stroke_fill=fill)

    def width(self, s: str, px: int) -> float:
        return _font(px * SUPERSAMPLE).getlength(s) / SUPERSAMPLE

    def png(self) -> bytes:
        out = io.BytesIO()
        self.image.resize((WIDTH, HEIGHT), Image.LANCZOS).save(out, "PNG", optimize=True)
        return out.getvalue()


def _wrap(pen: _Pen, marks: list[Mark], max_w: float, px: int) -> list[list[Mark]]:
    gap, lines, line, used = px * 0.5, [], [], 0.0
    for m in marks:
        w = pen.width(m.text, px)
        if line and used + gap + w > max_w:
            lines.append(line)
            line, used = [], 0.0
        used += (gap if line else 0) + w
        line.append(m)
    return lines + ([line] if line else [])


def _draw_marks(
    pen: _Pen, marks: list[Mark], center, box_w: float, box_h: float, sizes=(38, 34, 30, 26, 22, 19, 16)
) -> bool:
    """Draw the marks centred, shrinking the type until they fit the box. False if even the
    smallest size overflows (a crowded box); the marks are still drawn."""
    if not marks:
        return True
    fits = False
    for px in sizes:
        lines = _wrap(pen, marks, box_w, px)
        widest = max(sum(pen.width(m.text, px) for m in line) + px * 0.5 * (len(line) - 1) for line in lines)
        fits = len(lines) * px * LINE_HEIGHT <= box_h and widest <= box_w
        if fits:
            break
    cx, cy = center
    top = cy - len(lines) * px * LINE_HEIGHT / 2 + px * LINE_HEIGHT / 2
    for i, line in enumerate(lines):
        gap = px * 0.5
        total = sum(pen.width(m.text, px) for m in line) + gap * (len(line) - 1)
        x, y = cx - total / 2, top + i * px * LINE_HEIGHT
        for m in line:
            pen.text((x, y), m.text, px, RETRO if m.retrograde else WHITE, anchor="lm", bold=True)
            x += pen.width(m.text, px) + gap
    return fits


def _wrap_words(pen: _Pen, text: str, max_w: float, px: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and pen.width(trial, px) > max_w:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def _detail_lines(report: NatalReport) -> list[str]:
    b = report.birth
    return [f"Born {b.local:%d %b %Y}, {b.local:%H:%M}", b.place.label]


def _draw_details(pen: _Pen, report: NatalReport, center, width: float, px: int = 30):
    lines = [_detail_lines(report)[0], *_wrap_words(pen, _detail_lines(report)[1], width, px)]
    cx, cy = center
    y = cy - len(lines) * px * LINE_HEIGHT / 2 + px * LINE_HEIGHT / 2
    for line in lines:
        pen.text((cx, y), line, px, WHITE)
        y += px * LINE_HEIGHT


def _draw_south(pen: _Pen, report: NatalReport, degrees: bool) -> None:
    cell, x0, y0 = SIDE / 4, MARGIN, TOP
    marks, lagna = marks_by_sign(report, degrees), lagna_sign(report)
    for sign, (row, col) in SOUTH_CELLS.items():
        cx0, cy0 = x0 + col * cell, y0 + row * cell
        is_lagna = sign == lagna
        pen.rect(cx0, cy0, cx0 + cell, cy0 + cell, fill=PANEL if is_lagna else None, outline=GOLD,
                 width=7 if is_lagna else 3)
        pen.text((cx0 + cell / 2, cy0 + 24), SIGNS[sign], 22, GOLD_DIM)
        if is_lagna:
            pen.line([(cx0 + 6, cy0 + cell * 0.30), (cx0 + cell * 0.30, cy0 + 6)], GOLD, 4)
            asc = f"Asc {int(report.chart.ascendant % 30)}°" if degrees else "Asc"
            pen.text((cx0 + cell / 2, cy0 + cell - 24), asc, 24, GOLD, bold=True)
        _draw_marks(pen, marks[sign], (cx0 + cell / 2, cy0 + cell / 2 + 4), cell * 0.88, cell * 0.50)
    centre = (x0 + SIDE / 2, y0 + SIDE / 2)
    pen.rect(x0 + cell, y0 + cell, x0 + 3 * cell, y0 + 3 * cell, outline=GOLD, width=3)
    pen.text((centre[0], centre[1] - 90), "Rashi chart", 46, GOLD, bold=True)
    pen.text((centre[0], centre[1] - 45), "(D1)", 30, GOLD_DIM)
    _draw_details(pen, report, (centre[0], centre[1] + 40), cell * 1.8)


def _north_cells(x0: float, y0: float, s: float):
    """(polygon, marks centre, marks box w, h, sign-number position) for houses 1-12."""
    def pt(fx, fy):
        return (x0 + fx * s, y0 + fy * s)

    A, T, B, R = pt(0, 0), pt(.5, 0), pt(1, 0), pt(1, .5)
    C, Bt, D, L = pt(1, 1), pt(.5, 1), pt(0, 1), pt(0, .5)
    O, P1, P2, P3, P4 = pt(.5, .5), pt(.25, .25), pt(.75, .25), pt(.75, .75), pt(.25, .75)

    def diamond(poly, c):
        cx, cy = pt(*c)
        return poly, (cx, cy + .035 * s), .26 * s, .13 * s, (cx, cy - .085 * s)

    def triangle(poly, base, apex, horizontal):
        (bx, by), (ax, ay) = pt(*base), pt(*apex)
        centre = (bx + .42 * (ax - bx), by + .42 * (ay - by))
        number = (bx + .10 * (ax - bx), by + .10 * (ay - by))
        w, h = (.16 * s, .12 * s) if horizontal else (.12 * s, .16 * s)
        return poly, centre, w, h, number

    return [
        diamond([T, P1, O, P2], (.5, .25)),                       # 1
        triangle([A, T, P1], (.25, 0), (.25, .25), True),         # 2
        triangle([A, P1, L], (0, .25), (.25, .25), False),        # 3
        diamond([L, P1, O, P4], (.25, .5)),                       # 4
        triangle([L, P4, D], (0, .75), (.25, .75), False),        # 5
        triangle([D, P4, Bt], (.25, 1), (.25, .75), True),        # 6
        diamond([Bt, P4, O, P3], (.5, .75)),                      # 7
        triangle([Bt, P3, C], (.75, 1), (.75, .75), True),        # 8
        triangle([C, P3, R], (1, .75), (.75, .75), False),        # 9
        diamond([R, P3, O, P2], (.75, .5)),                       # 10
        triangle([R, P2, B], (1, .25), (.75, .25), False),        # 11
        triangle([B, P2, T], (.75, 0), (.75, .25), True),         # 12
    ]


def _draw_north(pen: _Pen, report: NatalReport, degrees: bool) -> None:
    x0, y0, s = MARGIN, TOP, SIDE
    cells = _north_cells(x0, y0, s)
    houses = north_houses(report, degrees)
    pen.polygon(cells[0][0], fill=PANEL)  # house 1 is the lagna
    pen.rect(x0, y0, x0 + s, y0 + s, outline=GOLD, width=5)
    pen.line([(x0, y0), (x0 + s, y0 + s)], GOLD, 3)
    pen.line([(x0 + s, y0), (x0, y0 + s)], GOLD, 3)
    pen.polygon([(x0 + s / 2, y0), (x0 + s, y0 + s / 2), (x0 + s / 2, y0 + s), (x0, y0 + s / 2)], outline=GOLD, width=3)
    for i, ((_, centre, box_w, box_h, number_at), (sign_number, marks)) in enumerate(zip(cells, houses, strict=True)):
        label = f"Asc {sign_number}" if i == 0 else str(sign_number)
        pen.text(number_at, label, 24, GOLD if i == 0 else GOLD_DIM, bold=i == 0)
        _draw_marks(pen, marks, centre, box_w, box_h)


def render_chart_png(report: NatalReport, style: str = "south", degrees: bool = False) -> bytes:
    """The chart as PNG bytes. `style` is 'south' or 'north'; `degrees` adds each planet's degree."""
    if style not in STYLES:
        raise ValueError(f"unknown chart style {style!r}; use one of {STYLES}")
    pen = _Pen()
    if style == "south":
        pen.text((WIDTH / 2, 80), "Birth chart · South Indian", 44, GOLD, bold=True)
        _draw_south(pen, report, degrees)
    else:
        pen.text((WIDTH / 2, 55), "Birth chart · North Indian", 44, GOLD, bold=True)
        pen.text((WIDTH / 2, 110), " · ".join(_detail_lines(report)), 26, WHITE)
        _draw_north(pen, report, degrees)
    y = TOP + SIDE + 50
    for line in LEGEND:
        pen.text((WIDTH / 2, y), line, 26, WHITE)
        y += 36
    return pen.png()
