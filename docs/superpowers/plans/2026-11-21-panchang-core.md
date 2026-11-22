# Panchang Core, Observance Days and Tulu Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute tithi, nakshatra, karana and yoga for a place and day, name observance days from per-observance rules stored as data (one primary date plus an attached alternate), add the Tulu month and day, answer panchang questions in chat, and make the morning message plain-language.

**Architecture:** Three pure engine modules (`panchang.py` elements and day facts, `observances.py` rule evaluation, `tulu.py`) driven by two profile files in `data/profiles/`. `service.py` turns them into report dataclasses, `render/panchang.py` words them, and `panchang_qa.py` routes questions to them. Observance day claims and explanations are gated by `verified` flags and entry verification levels, so unverified material is never shown.

**Tech Stack:** Python 3.12, frozen dataclasses, Skyfield + JPL DE440s (already bundled), PyYAML, pytest, ruff. Dev-only: `pyswisseph` for the golden-fixture generator (not a runtime dependency).

**Spec:** `docs/superpowers/specs/2026-11-21-panchang-core-design.md`. Read it first.

**Conventions (from CLAUDE.md):** engine modules never import `samay.service`, `samay.render` or `samay.bot`; wording lives in `render/`; disputed choices live in `data/profiles/*.yaml`; every sourced claim carries provenance. Before every commit run `uv run ruff check` and `uv run pytest -q` (after `scripts/fetch-ephemeris.sh` if `data/de440s.bsp` is missing). Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

**Verified starting facts (prototyped 2026-11-21):** for Pune (18.5196, 73.8553, Asia/Kolkata) the tithi at sunrise on 19, 20 and 21 Nov 2026 is 9, 10 and 12. Tithi 11 (Shukla Ekadashi) runs from about 07:16 on 20 Nov to about 06:32 on 21 Nov, so it is present at no sunrise: a real kshaya case used as the golden test below.

---

## Task 0: Owner gate (no code, run in parallel with Tasks 1-8)

This gate decides what "correct" means. Tasks 1-8 do not depend on it. **Tasks 9-12 must not ship to the family until it is done.**

- [ ] **Step 1: Identify the family's reference calendar.** Write in `research/notes/panchang-family-calendar.md`: the printed panchang or app the family uses, who decides Ekadashi dates, and which tradition it follows (`smarta`, `madhva` or `vaishnava`).
- [ ] **Step 2: Collect 10-15 real dates** from that calendar into `tests/fixtures/family_panchang_dates.yaml`, including some days where traditions split. Format:

```yaml
source: "<name of the printed panchang or app, and year>"
sampradaya: madhva            # the tradition that calendar follows
place: {name: Mangaluru, latitude: 12.9141, longitude: 74.856, tz: Asia/Kolkata}
dates:
  - {observance: ekadashi, date: 2026-11-20}
  - {observance: ekadashi, date: 2026-12-04}
known_divergences: []         # entries: {observance, date, cause}; filled in Task 14
```

- [ ] **Step 3: Collect 6-10 Tulu calendar anchors** into `tests/fixtures/tulu_anchors.yaml` (Bisu = Paggu 1, a sankranti day, Aati start, Pattanaje). Format:

```yaml
place: {name: Mangaluru, latitude: 12.9141, longitude: 74.856, tz: Asia/Kolkata}
anchors:
  - {date: 2026-04-14, month: Paggu, day: 1, source: "Bisu 2026 (mangaloreheritage.com Tulu calendar page)"}
```
  Add the family's own anchors with `source: family calendar`.
- [ ] **Step 4: Hand-send** two weeks of computed observances (after Task 9) to the family group and note who replies or compares with the printed copy. If nobody does, stop after Task 10 and deliver a static table instead of Tasks 11-12.
- [ ] **Step 5: Commit** the notes and fixtures.

---

## File structure

| File | Responsibility |
|---|---|
| `samay/engine/daylight.py` (modify) | Sunrise/sunset with a selectable sunrise definition |
| `samay/engine/panchang.py` (create) | `Site`, `Element`, `element_at`, `DayFacts`, `day_facts`, names |
| `samay/engine/observances.py` (create) | `Rule`, `Viddha`, `Observance`, `observances_between`, `observances_for`, `find_next` |
| `samay/engine/panchang_profile.py` (create) | Load and validate `data/profiles/panchang-family.yaml` |
| `samay/engine/tulu.py` (create) | Sun ingress, Tulu month and day, tulu profile loader |
| `samay/engine/errors.py` (modify) | `SampradayaNotSet` |
| `data/profiles/panchang-family.yaml`, `data/profiles/tulu.yaml` (create) | All disputed choices |
| `scripts/golden_panchang.py`, `scripts/measure_margin.py` (create) | Dev tools |
| `samay/models.py` (modify) | `PanchangReport`, `NextObservanceReport` |
| `samay/service.py` (modify) | `panchang_report`, `next_observance_report`, `reference_place`, `observance_explanation` |
| `samay/render/panchang.py` (create) | All panchang wording and the plain-language brief |
| `samay/render/text.py` (modify) | `render_brief` delegates to the new wording |
| `samay/panchang_qa.py` (create) | Table-driven question sorter and answer assembly |
| `samay/bot/app.py` (modify) | Hook before the birth-chart router; brief composition |
| `data/entries/panchang-observances.yaml` (create) | Bharani and Krittika entries (unchecked until promoted) |

---

## Task 1: Selectable sunrise definition

**Files:** Modify `samay/engine/daylight.py` (the `sun_times` function). Test: `tests/test_daylight.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_daylight.py`)

```python
def test_disc_centre_sunrise_is_later_and_sunset_earlier_than_upper_limb():
    day = date(2026, 11, 21)
    upper = daylight.sun_times(18.5196, 73.8553, "Asia/Kolkata", day)
    centre = daylight.sun_times(18.5196, 73.8553, "Asia/Kolkata", day, definition="disc_centre")
    assert timedelta(seconds=30) < centre.sunrise - upper.sunrise < timedelta(seconds=120)
    assert timedelta(seconds=30) < upper.sunset - centre.sunset < timedelta(seconds=120)


def test_unknown_sunrise_definition_is_rejected():
    with pytest.raises(ValueError, match="sunrise definition"):
        daylight.sun_times(18.5196, 73.8553, "Asia/Kolkata", date(2026, 11, 21), definition="moonlight")
```

- [ ] **Step 2: Run, expect FAIL.** `uv run pytest tests/test_daylight.py -q -k "disc_centre or unknown_sunrise"` → `TypeError: sun_times() got an unexpected keyword argument 'definition'`.

- [ ] **Step 3: Implement.** In `daylight.py` add below `PARTS = 8`:

```python
# Horizon altitude of the Sun's centre at the moment the rule counts as rise or set.
# upper_limb: top edge on the horizon with standard refraction (34' + 16' semidiameter). disc_centre: centre, 34' refraction.
HORIZON_DEGREES = {"upper_limb": -0.8333, "disc_centre": -0.5667}
```

Change the signature and the line that builds `is_up`:

```python
def sun_times(latitude: float, longitude: float, tz: str, day: date, definition: str = "upper_limb") -> SunTimes | None:
    """..."""  # keep the existing docstring
    if definition not in HORIZON_DEGREES:
        raise ValueError(f"unknown sunrise definition {definition!r}")
    zone = ZoneInfo(tz)
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    ts = ephemeris._timescale()
    kernel, topos = ephemeris._kernel(), wgs84.latlon(latitude, longitude)
    if definition == "upper_limb":
        is_up = almanac.sunrise_sunset(kernel, topos)
    else:
        is_up = almanac.risings_and_settings(kernel, kernel["sun"], topos, horizon_degrees=HORIZON_DEGREES[definition])
```

Leave the rest of the function unchanged.

- [ ] **Step 4: Run all daylight tests, expect PASS.** `uv run pytest tests/test_daylight.py -q` (the existing golden and published-figure tests prove the default is unchanged).

- [ ] **Step 5: Commit.** `git add samay/engine/daylight.py tests/test_daylight.py && git commit -m "feat: selectable sunrise definition (upper limb or disc centre)"`

---

## Task 2: Panchang elements at an instant

**Files:** Create `samay/engine/panchang.py`. Test: `tests/test_panchang.py`.

- [ ] **Step 1: Write the failing tests** (`tests/test_panchang.py`)

```python
from datetime import UTC, datetime, timedelta

import pytest

from samay.engine import panchang
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
IST = timedelta(hours=5, minutes=30)


def ist(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC) - IST


def test_shukla_ekadashi_at_pune_sunrise_boundaries_on_20_21_nov_2026():
    e = panchang.element_at("tithi", ist(20, 12, 0))  # midday on 20 Nov IST
    assert (e.number, e.name) == (11, "Shukla Ekadashi")
    assert abs(e.start - ist(20, 7, 16)) < timedelta(minutes=2)
    assert abs(e.end - ist(21, 6, 32)) < timedelta(minutes=2)


def test_nakshatra_and_its_boundaries():
    e = panchang.element_at("nakshatra", datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    assert (e.number, e.name) == (27, "Revati")
    assert abs(e.start - datetime(2026, 11, 21, 1, 20, 39, tzinfo=UTC)) < timedelta(minutes=2)
    assert abs(e.end - datetime(2026, 11, 22, 0, 24, 55, tzinfo=UTC)) < timedelta(minutes=2)


def test_elements_tile_time_without_gaps_or_overlaps():
    t = datetime(2026, 11, 1, tzinfo=UTC)
    seen = []
    for _ in range(8):
        e = panchang.element_at("tithi", t)
        seen.append(e)
        t = e.end + timedelta(seconds=1)
    for a, b in zip(seen, seen[1:], strict=False):
        assert b.start - a.end < timedelta(seconds=3)
        assert b.number == a.number % 30 + 1


def test_karana_and_yoga_have_expected_ranges_and_names():
    k = panchang.element_at("karana", datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    y = panchang.element_at("yoga", datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    assert 1 <= k.number <= 60 and k.name in panchang.KARANA_MOVABLE + panchang.KARANA_FIXED
    assert 1 <= y.number <= 27 and y.name == panchang.YOGA_NAMES[y.number - 1]


@pytest.mark.parametrize("number, name", [(1, "Shukla Pratipada"), (11, "Shukla Ekadashi"), (15, "Purnima"),
                                            (16, "Krishna Pratipada"), (26, "Krishna Ekadashi"), (30, "Amavasya")])
def test_tithi_names(number, name):
    assert panchang.tithi_name(number) == name


def test_karana_sequence_has_the_fixed_ones_at_the_ends():
    assert panchang.karana_name(0) == "Kimstughna"
    assert [panchang.karana_name(i) for i in (1, 2, 8)] == ["Bava", "Balava", "Bava"]
    assert [panchang.karana_name(i) for i in (57, 58, 59)] == ["Shakuni", "Chatushpada", "Naga"]


def test_outside_the_ephemeris_range_is_a_plain_error():
    from samay.engine.errors import OutOfEphemerisRange

    with pytest.raises(OutOfEphemerisRange):
        panchang.element_at("tithi", datetime(2200, 1, 1, tzinfo=UTC))
```

- [ ] **Step 2: Run, expect FAIL** (`ImportError: cannot import name 'panchang'`). `uv run pytest tests/test_panchang.py -q`

- [ ] **Step 3: Implement `samay/engine/panchang.py`**

```python
"""Tithi, nakshatra, karana and yoga for any instant, found by searching the Sun and Moon's sidereal longitudes.

A tithi is each 12 degrees the Moon gains on the Sun, a karana half of that, a nakshatra 13 deg 20' of the Moon's
longitude, a yoga each 13 deg 20' of the Sun's plus the Moon's. These are geocentric, so they do not depend on the
place; the day a tithi counts for does (see observances.py). Searches go 2 hours at a time, then bisect to a second.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from . import daylight, ephemeris
from .vedic import NAKSHATRAS

TITHI_DEG = 12.0
KARANA_DEG = 6.0
NAK_DEG = YOGA_DEG = 360.0 / 27.0
COARSE_STEP = timedelta(hours=2)
SEARCH_LIMIT = timedelta(hours=48)
RESOLUTION = timedelta(seconds=1)

TITHI_NAMES = ("Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami", "Ashtami",
               "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi")
KARANA_MOVABLE = ("Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti")
KARANA_FIXED = ("Kimstughna", "Shakuni", "Chatushpada", "Naga")
YOGA_NAMES = ("Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", "Dhriti", "Shula",
              "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana",
              "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti")


def tithi_name(number: int) -> str:
    """1-15 are Shukla (waxing), 16-30 Krishna (waning); the 15th of each is Purnima or Amavasya."""
    index = (number - 1) % 15
    if index == 14:
        return "Purnima" if number == 15 else "Amavasya"
    return f"{'Shukla' if number <= 15 else 'Krishna'} {TITHI_NAMES[index]}"


def karana_name(cell: int) -> str:
    """cell is 0-59, the half-tithi count from new moon: Kimstughna first, seven movable karanas repeating, then three fixed."""
    if cell == 0:
        return "Kimstughna"
    if cell >= 57:
        return KARANA_FIXED[cell - 56]
    return KARANA_MOVABLE[(cell - 1) % 7]


def _elongation(sun: float, moon: float) -> float:
    return (moon - sun) % 360.0


# kind -> (angle as a function of (sun, moon) sidereal longitudes, width of one element in degrees)
QUANTITIES = {
    "tithi": (_elongation, TITHI_DEG),
    "karana": (_elongation, KARANA_DEG),
    "nakshatra": (lambda sun, moon: moon % 360.0, NAK_DEG),
    "yoga": (lambda sun, moon: (sun + moon) % 360.0, YOGA_DEG),
}


@dataclass(frozen=True)
class Site:
    latitude: float
    longitude: float  # east positive
    tz: str


@dataclass(frozen=True)
class Element:
    kind: str  # tithi | nakshatra | karana | yoga
    number: int  # 1-based; karana is 1-60
    name: str
    start: datetime  # UTC
    end: datetime  # UTC


def _longitudes(times: list[datetime], ayanamsa: str) -> list[tuple[float, float]]:
    track = ephemeris.sidereal_track(times, ayanamsa)
    return list(zip(track["sun"], track["moon"], strict=True))


def _edge(kind: str, t0: datetime, forward: bool, ayanamsa: str) -> datetime:
    """The instant the element holding t0 begins (forward=False) or ends (forward=True), to a second."""
    angle, width = QUANTITIES[kind]
    sign = 1 if forward else -1
    grid = [t0 + sign * COARSE_STEP * i for i in range(int(SEARCH_LIMIT / COARSE_STEP) + 1)]
    values = [angle(s, m) for s, m in _longitudes(grid, ayanamsa)]
    base = int(values[0] // width)
    for i in range(1, len(grid)):
        if int(values[i] // width) != base:
            inside, outside = grid[i - 1], grid[i]
            break
    else:
        raise RuntimeError(f"no {kind} boundary within {SEARCH_LIMIT} of {t0}")
    while abs(outside - inside) > RESOLUTION:
        mid = inside + (outside - inside) / 2
        if int(angle(*_longitudes([mid], ayanamsa)[0]) // width) == base:
            inside = mid
        else:
            outside = mid
    return outside if forward else inside


def _name(kind: str, cell: int) -> str:
    if kind == "tithi":
        return tithi_name(cell + 1)
    if kind == "nakshatra":
        return NAKSHATRAS[cell]
    if kind == "karana":
        return karana_name(cell)
    return YOGA_NAMES[cell]


def element_at(kind: str, utc: datetime, ayanamsa: str = "lahiri_mean") -> Element:
    angle, width = QUANTITIES[kind]
    cell = int(angle(*_longitudes([utc], ayanamsa)[0]) // width)
    return Element(kind, cell + 1, _name(kind, cell), _edge(kind, utc, False, ayanamsa), _edge(kind, utc, True, ayanamsa))
```

- [ ] **Step 4: Run, expect PASS.** `uv run pytest tests/test_panchang.py -q`

- [ ] **Step 5: Commit.** `git add samay/engine/panchang.py tests/test_panchang.py && git commit -m "feat: tithi, nakshatra, karana and yoga with start and end times"`

---

## Task 3: Day facts for a place (local sunrise and sunset)

**Files:** Modify `samay/engine/panchang.py` (append). Test: `tests/test_panchang.py` (append).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_panchang.py`)

```python
from datetime import date

PUNE = panchang.Site(18.5196, 73.8553, "Asia/Kolkata")


def test_day_facts_use_local_sunrise_and_name_the_prevailing_elements():
    facts = panchang.day_facts(PUNE, date(2026, 11, 21))
    assert facts.sunrise.tzinfo is not None and facts.sunrise.utcoffset() == IST
    assert facts.sunrise.strftime("%H:%M") == "06:44" and facts.sunset.strftime("%H:%M") == "17:56"
    assert facts.tithi.name == "Shukla Dwadashi"
    assert facts.nakshatra.name == "Uttara Bhadrapada"  # Revati only begins at 06:50, six minutes after this sunrise


def test_ekadashi_is_at_no_sunrise_on_20_or_21_nov_in_pune():
    assert panchang.day_facts(PUNE, date(2026, 11, 20)).tithi.number == 10
    assert panchang.day_facts(PUNE, date(2026, 11, 21)).tithi.number == 12


def test_the_sunrise_definition_comes_from_the_caller():
    upper = panchang.day_facts(PUNE, date(2026, 11, 21))
    centre = panchang.day_facts(PUNE, date(2026, 11, 21), definition="disc_centre")
    assert centre.sunrise > upper.sunrise


def test_dst_changes_the_local_offset_of_the_sunrise_across_the_clock_change():
    chicago = panchang.Site(44.953, -93.023, "America/Chicago")  # US clocks went back on 1 Nov 2026
    assert panchang.day_facts(chicago, date(2026, 10, 31)).sunrise.utcoffset() == timedelta(hours=-5)
    assert panchang.day_facts(chicago, date(2026, 11, 2)).sunrise.utcoffset() == timedelta(hours=-6)


def test_southern_hemisphere_place_works():
    sydney = panchang.Site(-33.8688, 151.2093, "Australia/Sydney")
    facts = panchang.day_facts(sydney, date(2026, 11, 21))
    assert facts.sunrise.utcoffset() == timedelta(hours=11) and 5 <= facts.sunrise.hour <= 6


def test_polar_day_without_a_sunrise_gives_none():
    assert panchang.day_facts(panchang.Site(69.65, 18.96, "Europe/Oslo"), date(2026, 12, 21)) is None
```

- [ ] **Step 2: Run, expect FAIL** (`AttributeError: module has no attribute 'Site'`... `day_facts`). `uv run pytest tests/test_panchang.py -q -k "day_facts or no_sunrise or dst or southern or polar"`

- [ ] **Step 3: Implement** (append to `panchang.py`)

```python
@dataclass(frozen=True)
class DayFacts:
    day: date  # local calendar day
    sunrise: datetime  # local, timezone-aware
    sunset: datetime
    tithi: Element  # the elements prevailing at local sunrise
    nakshatra: Element
    karana: Element
    yoga: Element


def day_facts(site: Site, day: date, ayanamsa: str = "lahiri_mean", definition: str = "upper_limb") -> DayFacts | None:
    """What prevails at the place's own sunrise on a local calendar day; None when the Sun does not rise and set."""
    sun = daylight.sun_times(site.latitude, site.longitude, site.tz, day, definition)
    if sun is None:
        return None
    at = sun.sunrise.astimezone(UTC)
    return DayFacts(day, sun.sunrise, sun.sunset, *(element_at(k, at, ayanamsa) for k in ("tithi", "nakshatra", "karana", "yoga")))
```

- [ ] **Step 4: Run, expect PASS.** `uv run pytest tests/test_panchang.py -q`

- [ ] **Step 5: Commit.** `git add samay/engine/panchang.py tests/test_panchang.py && git commit -m "feat: panchang day facts at the local sunrise"`

---

## Task 4: Observance rules (window primitive, kshaya, vriddhi, alternates, margin)

**Files:** Create `samay/engine/observances.py`; modify `samay/engine/errors.py`. Test: `tests/test_observances.py`.

- [ ] **Step 1: Add the error.** Append to `samay/engine/errors.py`:

```python
class SampradayaNotSet(SamayError):
    """The family's tradition has not been chosen, so no observance day can be named."""
```

- [ ] **Step 2: Write the failing tests** (`tests/test_observances.py`)

```python
from datetime import date

import pytest

from samay.engine.errors import SampradayaNotSet
from samay.engine.observances import Rule, Viddha, find_next, observances_between, observances_for
from samay.engine.paths import EPHEMERIS_PATH
from samay.engine.panchang import Site

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE = Site(18.5196, 73.8553, "Asia/Kolkata")
NOV_DEC = (date(2026, 11, 1), date(2026, 12, 31))
EKADASHI = Rule(tithis=(11, 26))


def summary(found):
    return [(o.primary, o.kind, [(a.day, a.reason) for a in o.alternates]) for o in found]


def test_sunrise_rule_marks_a_kshaya_ekadashi_and_attaches_the_other_day():
    found = observances_between(EKADASHI, PUNE, *NOV_DEC, margin_minutes=3)
    assert summary(found) == [
        (date(2026, 11, 5), "single", []),
        (date(2026, 11, 20), "kshaya", [(date(2026, 11, 21), "kshaya")]),
        (date(2026, 12, 4), "single", []),
        (date(2026, 12, 20), "single", []),
    ]


def test_kshaya_can_be_resolved_to_the_next_day_instead():
    rule = Rule(tithis=(11, 26), on_kshaya="next_day")
    kshaya = [o for o in observances_between(rule, PUNE, *NOV_DEC) if o.kind == "kshaya"][0]
    assert kshaya.primary == date(2026, 11, 21) and kshaya.alternates[0].day == date(2026, 11, 20)


def test_kshaya_can_make_no_claim():
    rule = Rule(tithis=(11, 26), on_kshaya="none")
    kshaya = [o for o in observances_between(rule, PUNE, *NOV_DEC) if o.kind == "kshaya"][0]
    assert kshaya.primary is None


def test_dashami_viddha_rejects_the_day_and_pushes_the_observance_on():
    viddha = Viddha(tithis=(10, 25), anchor="sunrise", start_minutes=-96, end_minutes=0)
    rule = Rule(tithis=(11, 26), on_kshaya="next_day", viddha=viddha)
    found = observances_between(rule, PUNE, *NOV_DEC)
    assert [o.primary for o in found] == [date(2026, 11, 5), date(2026, 11, 21), date(2026, 12, 4), date(2026, 12, 20)]


def test_a_window_spanning_two_sunrises_is_a_vriddhi_with_a_choice_of_day():
    wide = dict(tithis=(11, 26), anchor="sunrise", start_minutes=-2880, end_minutes=0)
    first = [o for o in observances_between(Rule(**wide), PUNE, *NOV_DEC) if o.kind == "vriddhi"][0]
    last = [o for o in observances_between(Rule(**wide, on_vriddhi="last"), PUNE, *NOV_DEC) if o.kind == "vriddhi"][0]
    assert (first.primary, first.alternates[0].day) == (date(2026, 11, 21), date(2026, 11, 22))
    assert (last.primary, last.alternates[0].day) == (date(2026, 11, 22), date(2026, 11, 21))


def test_pradosha_window_after_sunset():
    rule = Rule(tithis=(13, 28), anchor="sunset", start_minutes=0, end_minutes=72)
    found = observances_between(rule, PUNE, date(2026, 11, 1), date(2026, 12, 15))
    assert [o.primary for o in found] == [date(2026, 11, 6), date(2026, 11, 22), date(2026, 12, 6)]


def test_a_boundary_inside_the_margin_adds_a_calculation_alternate():
    # With a huge margin every sunrise-instant decision is within reach of the next day's sunrise.
    found = observances_between(EKADASHI, PUNE, date(2026, 12, 3), date(2026, 12, 5), margin_minutes=24 * 60)
    assert any(a.reason == "calculation" for o in found for a in o.alternates)


def test_sampradaya_picks_the_rule_and_the_other_traditions_become_named_alternates():
    rules = {
        "smarta": Rule(tithis=(11, 26), on_kshaya="start_day"),
        "madhva": Rule(tithis=(11, 26), on_kshaya="next_day"),
    }
    found = observances_for(rules, "smarta", PUNE, *NOV_DEC)
    kshaya = [o for o in found if o.kind == "kshaya"][0]
    assert kshaya.primary == date(2026, 11, 20)
    assert [(a.day, a.reason) for a in kshaya.alternates if a.reason == "madhva convention"] == [(date(2026, 11, 21), "madhva convention")]


def test_no_sampradaya_means_no_day_is_named():
    with pytest.raises(SampradayaNotSet):
        observances_for({"smarta": EKADASHI, "madhva": EKADASHI}, None, PUNE, *NOV_DEC)


def test_a_rule_that_does_not_depend_on_tradition_needs_none():
    assert observances_for({"all": EKADASHI}, None, PUNE, *NOV_DEC)


def test_find_next_returns_the_first_upcoming_day():
    nxt = find_next({"all": EKADASHI}, None, PUNE, date(2026, 11, 6))
    assert nxt.primary == date(2026, 11, 20)
    assert find_next({"all": Rule(tithis=(11, 26), on_kshaya="none")}, None, PUNE, date(2026, 11, 6)).primary == date(2026, 12, 4)
```

- [ ] **Step 3: Run, expect FAIL** (`ModuleNotFoundError: samay.engine.observances`). `uv run pytest tests/test_observances.py -q`

- [ ] **Step 4: Implement `samay/engine/observances.py`**

```python
"""Which local day an observance falls on, from a rule stored as data.

A rule names the tithis it is about, an anchor (local sunrise or sunset) and a window measured from that anchor in
minutes. A zero-length window is an instant: the tithi must be current at the anchor. A longer window needs the
tithi to overlap it. The result is always one primary day plus, where the rule is ambiguous, an alternate:
  kshaya  - the tithi is current at no anchor, so on_kshaya picks start_day, next_day or none (no claim);
  vriddhi - it qualifies on two days, so on_vriddhi picks first or last;
  calculation - the outcome changes if the anchor moves by the profile's margin, so the other day is attached;
  "<tradition> convention" - another tradition's rule gives a different day.
Which tradition is right for a family is data (the profile's sampradaya), never a default in code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import daylight
from .errors import SampradayaNotSet
from .panchang import Site, element_at

ANCHORS = ("sunrise", "sunset")
KSHAYA_CHOICES = ("start_day", "next_day", "none")
VRIDDHI_CHOICES = ("first", "last")
SEARCH_DAYS = 70  # long enough for the rarest observance here (Amavasya, about 30 days apart)


@dataclass(frozen=True)
class Viddha:
    """A day is rejected when one of these tithis overlaps the window (for example Dashami before dawn)."""
    tithis: tuple[int, ...]
    anchor: str
    start_minutes: int
    end_minutes: int


@dataclass(frozen=True)
class Rule:
    tithis: tuple[int, ...]  # tithi numbers 1-30 (Shukla Ekadashi is 11, Krishna Ekadashi 26)
    anchor: str = "sunrise"
    start_minutes: int = 0
    end_minutes: int = 0
    on_kshaya: str = "start_day"
    on_vriddhi: str = "first"
    viddha: Viddha | None = None


@dataclass(frozen=True)
class Alternate:
    day: date
    reason: str  # kshaya | vriddhi | calculation | "<tradition> convention"


@dataclass(frozen=True)
class Observance:
    primary: date | None  # None when the rule chose to make no claim
    kind: str  # single | kshaya | vriddhi
    alternates: tuple[Alternate, ...]
    tithi_start: datetime  # UTC
    tithi_end: datetime


@lru_cache(maxsize=4096)
def _sun(latitude: float, longitude: float, tz: str, day: date, definition: str):
    return daylight.sun_times(latitude, longitude, tz, day, definition)


def _anchor(site: Site, day: date, anchor: str, definition: str) -> datetime | None:
    sun = _sun(site.latitude, site.longitude, site.tz, day, definition)
    if sun is None:
        return None
    return sun.sunrise if anchor == "sunrise" else sun.sunset


def _tithis_in(start: datetime, end: datetime, ayanamsa: str) -> set[int]:
    current = element_at("tithi", start, ayanamsa)
    found = {current.number}
    while current.end < end:
        current = element_at("tithi", current.end + timedelta(seconds=1), ayanamsa)
        found.add(current.number)
    return found


def _qualifies(rule: Rule, start: datetime, end: datetime, site: Site, day: date, ayanamsa: str, definition: str,
               delta: int) -> bool:
    anchor = _anchor(site, day, rule.anchor, definition)
    if anchor is None:
        return False
    anchor += timedelta(minutes=delta)
    w0, w1 = anchor + timedelta(minutes=rule.start_minutes), anchor + timedelta(minutes=rule.end_minutes)
    hit = start <= w0 < end if rule.start_minutes == rule.end_minutes else max(start, w0) < min(end, w1)
    if hit and rule.viddha is not None:
        v = rule.viddha
        v_anchor = _anchor(site, day, v.anchor, definition)
        if v_anchor is not None:
            v_anchor += timedelta(minutes=delta)
            v0, v1 = v_anchor + timedelta(minutes=v.start_minutes), v_anchor + timedelta(minutes=v.end_minutes)
            if _tithis_in(v0, max(v0, v1), ayanamsa) & set(v.tithis):
                return False
    return hit


def _qualified_days(rule: Rule, start: datetime, end: datetime, site: Site, ayanamsa: str, definition: str,
                    delta: int) -> list[date]:
    zone = ZoneInfo(site.tz)
    day = (start.astimezone(zone) - timedelta(days=1)).date()
    last = (end.astimezone(zone) + timedelta(days=1)).date()
    days = []
    while day <= last:
        if _qualifies(rule, start, end, site, day, ayanamsa, definition, delta):
            days.append(day)
        day += timedelta(days=1)
    return days


def _reduce(rule: Rule, qualified: list[date], start: datetime, zone: ZoneInfo) -> tuple[str, date | None, list[date]]:
    if len(qualified) == 1:
        return "single", qualified[0], []
    if not qualified:
        start_day = start.astimezone(zone).date()
        if rule.on_kshaya == "none":
            return "kshaya", None, []
        following = start_day + timedelta(days=1)
        if rule.on_kshaya == "start_day":
            return "kshaya", start_day, [following]
        return "kshaya", following, [start_day]
    first, last = qualified[0], qualified[-1]
    return ("vriddhi", first, [last]) if rule.on_vriddhi == "first" else ("vriddhi", last, [first])


def observances_between(rule: Rule, site: Site, first: date, last: date, ayanamsa: str = "lahiri_mean",
                        margin_minutes: int = 0, definition: str = "upper_limb") -> list[Observance]:
    """Every occurrence of the rule's tithis that touches [first, last], each resolved to a primary day."""
    zone = ZoneInfo(site.tz)
    begin = datetime(first.year, first.month, first.day, tzinfo=zone).astimezone(UTC) - timedelta(days=1)
    stop = datetime(last.year, last.month, last.day, tzinfo=zone).astimezone(UTC) + timedelta(days=2)
    found = []
    tithi = element_at("tithi", begin, ayanamsa)
    while tithi.start < stop:
        if tithi.number in rule.tithis:
            kind, primary, others = _reduce(rule, _qualified_days(rule, tithi.start, tithi.end, site, ayanamsa, definition, 0),
                                            tithi.start, zone)
            alternates = [Alternate(d, kind) for d in others]
            for delta in ((-margin_minutes, margin_minutes) if margin_minutes else ()):
                _, shifted, _ = _reduce(rule, _qualified_days(rule, tithi.start, tithi.end, site, ayanamsa, definition, delta),
                                        tithi.start, zone)
                if shifted is not None and shifted != primary and all(a.day != shifted for a in alternates):
                    alternates.append(Alternate(shifted, "calculation"))
            days = ([primary] if primary else []) + [a.day for a in alternates]
            if any(first <= d <= last for d in days):
                found.append(Observance(primary, kind, tuple(alternates), tithi.start, tithi.end))
        tithi = element_at("tithi", tithi.end + timedelta(seconds=1), ayanamsa)
    return found


def observances_for(rules: dict[str, Rule], sampradaya: str | None, site: Site, first: date, last: date,
                    ayanamsa: str = "lahiri_mean", margin_minutes: int = 0, definition: str = "upper_limb") -> list[Observance]:
    """Apply the family's tradition. `rules` maps a tradition name to its rule, or holds just "all" when the observance
    does not differ between traditions. Other traditions' days appear as named alternates."""
    if "all" in rules:
        chosen = "all"
    elif sampradaya is None:
        raise SampradayaNotSet("the family's tradition has not been set")
    elif sampradaya not in rules:
        raise ValueError(f"no rule for tradition {sampradaya!r}")
    else:
        chosen = sampradaya
    primary = observances_between(rules[chosen], site, first, last, ayanamsa, margin_minutes, definition)
    others = {name: {o.tithi_start: o for o in observances_between(rule, site, first, last, ayanamsa, margin_minutes, definition)}
              for name, rule in rules.items() if name != chosen}
    merged = []
    for o in primary:
        extra = []
        for name, table in others.items():
            twin = table.get(o.tithi_start)
            if twin is not None and twin.primary is not None and twin.primary != o.primary \
                    and all(a.day != twin.primary for a in o.alternates):
                extra.append(Alternate(twin.primary, f"{name} convention"))
        merged.append(Observance(o.primary, o.kind, o.alternates + tuple(extra), o.tithi_start, o.tithi_end))
    return merged


def find_next(rules: dict[str, Rule], sampradaya: str | None, site: Site, after: date, ayanamsa: str = "lahiri_mean",
              margin_minutes: int = 0, definition: str = "upper_limb") -> Observance | None:
    """The first observance whose primary day is on or after `after`."""
    found = observances_for(rules, sampradaya, site, after, after + timedelta(days=SEARCH_DAYS), ayanamsa,
                            margin_minutes, definition)
    upcoming = [o for o in found if o.primary is not None and o.primary >= after]
    return min(upcoming, key=lambda o: o.primary, default=None)
```

- [ ] **Step 5: Run, expect PASS.** `uv run pytest tests/test_observances.py -q`. If `test_a_boundary_inside_the_margin_adds_a_calculation_alternate` fails, the margin of 24 h should shift every decision by a day; check that `_qualified_days` is passing `delta` to `_qualifies`.

- [ ] **Step 6: Commit.** `git add samay/engine/observances.py samay/engine/errors.py tests/test_observances.py && git commit -m "feat: per-observance day rules with window, kshaya, vriddhi, viddha and alternates"`

---

## Task 4b: Make the observance search fast enough for chat (added during execution)

Task 4's implementer measured about 8-10 s for one two-month `observances_between` call (and about 9 s for `find_next`), mostly in repeated `element_at` bisection and per-day sun-time searches. That is too slow for a chat answer, so before Task 9 wires it into the bot:

- [ ] **Step 1: Profile.** `uv run python -X importtime`-style is not needed; use `cProfile` on `observances_between(Rule(tithis=(11, 26)), PUNE, date(2026, 11, 1), date(2026, 12, 31))` and record where the time goes in the commit message.
- [ ] **Step 2: Cut the cost without changing any result.** Likely wins: vectorise the bisection (evaluate a grid of candidate instants in one `sidereal_track` call and narrow in 3-4 rounds instead of about 13 single-instant calls), and cache `element_at` by (kind, tithi start) so each tithi is searched once per run. The existing tests are the guard: all of them must still pass unchanged.
- [ ] **Step 3: Add a timing guard.** A test that `observances_between` for two months finishes under 5 s and `find_next` under 3 s (skip when `CI` sets `SAMAY_SLOW_CI=1`).
- [ ] **Step 4: Commit.** `git commit -m "perf: faster tithi search for observance days"`.

---

## Task 5: Panchang profile and the shipped conventions

**Files:** Create `data/profiles/panchang-family.yaml`, `samay/engine/panchang_profile.py`. Test: `tests/test_panchang_profile.py`.

The shipped rule values are **provisional and unverified** (`verified: false`): they let the engine run, but the bot makes no day claim from them until Task 13 verifies each against a source. The Madhva Ekadashi variant and the Pradosha window length are the main unverified values.

- [ ] **Step 1: Write the failing tests** (`tests/test_panchang_profile.py`)

```python
import pytest
import yaml

from samay.engine.panchang_profile import load_panchang_profile
from samay.engine.paths import PROFILES_DIR


def write(tmp_path, **changes):
    raw = yaml.safe_load((PROFILES_DIR / "panchang-family.yaml").read_text())
    raw.update(changes)
    (tmp_path / "panchang-family.yaml").write_text(yaml.safe_dump(raw))
    load_panchang_profile.cache_clear()
    return tmp_path


def test_shipped_profile_loads_and_has_no_default_tradition():
    p = load_panchang_profile()
    assert p.sampradaya is None
    assert set(p.observances) == {"ekadashi", "pradosha", "purnima", "amavasya"}
    assert p.observances["ekadashi"].rules["madhva"].viddha is not None
    assert p.observances["pradosha"].rules["all"].anchor == "sunset"
    assert p.margin_minutes >= 0 and p.sunrise_definition in ("upper_limb", "disc_centre")


def test_every_shipped_rule_is_marked_unverified_until_sourced():
    assert not any(o.verified for o in load_panchang_profile().observances.values())


@pytest.mark.parametrize("field, value", [("sampradaya", "zoroastrian"), ("ayanamsa", "fagan"),
                                           ("sunrise_definition", "moonrise"), ("ambiguity_margin_minutes", -1)])
def test_bad_values_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError, match=field.split("_")[0]):
        load_panchang_profile(directory=write(tmp_path, **{field: value}))


def test_a_rule_with_a_bad_choice_is_rejected(tmp_path):
    raw = yaml.safe_load((PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["ekadashi"]["rules"]["madhva"]["on_kshaya"] = "tomorrow-ish"
    write(tmp_path, observances=raw["observances"])
    with pytest.raises(ValueError, match="on_kshaya"):
        load_panchang_profile(directory=tmp_path)
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError`). `uv run pytest tests/test_panchang_profile.py -q`

- [ ] **Step 3: Create `data/profiles/panchang-family.yaml`**

```yaml
# Panchang conventions for the family. Every disputed choice lives here, not in code.
# `sampradaya` has NO default: until it is set (smarta | madhva | vaishnava) the bot gives tithis and nakshatras
# but names no observance day. Set it after Task 0 identifies the family's printed panchang.
id: panchang-family
name: Family panchang conventions
sampradaya: null
ayanamsa: lahiri_mean
sunrise_definition: upper_limb      # upper_limb | disc_centre (standard 34' refraction)
# Calculation spread only (sunrise definition, ayanamsa, ephemeris). PROVISIONAL until Task 8 replaces it with the
# measured value from scripts/measure_margin.py. Rule differences between traditions are never absorbed here.
ambiguity_margin_minutes: 3
observances:
  ekadashi:
    label: Ekadashi
    # Every value below is UNVERIFIED. Smarta: the tithi current at local sunrise governs the day (Dharmasindhu, per the
    # Kamakoti English summary, ch. 3). Madhva: as Smarta but a day is rejected when Dashami touches the 96 minutes
    # (4 ghatikas) before sunrise (arunodaya). Task 13 reads the texts and sets verified: true or changes these.
    verified: false
    source: {text: "Dharmasindhu; Nirnaya Sindhu", locus: null}
    rules:
      smarta: {tithis: [11, 26], anchor: sunrise, start_minutes: 0, end_minutes: 0, on_kshaya: start_day, on_vriddhi: first}
      madhva:
        tithis: [11, 26]
        anchor: sunrise
        start_minutes: 0
        end_minutes: 0
        on_kshaya: next_day
        on_vriddhi: first
        viddha: {tithis: [10, 25], anchor: sunrise, start_minutes: -96, end_minutes: 0}
  pradosha:
    label: Pradosha
    # UNVERIFIED window: dusk on Trayodashi. 72 minutes (3 ghatikas) after sunset is one common reading; some texts
    # give a longer span. Task 13 fixes it from the Skanda Purana passage (Brahma Khanda vv. 5-14) and a digest.
    verified: false
    source: {text: "Skanda Purana, Brahma Khanda", locus: "vv. 5-14"}
    rules:
      all: {tithis: [13, 28], anchor: sunset, start_minutes: 0, end_minutes: 72, on_kshaya: start_day, on_vriddhi: first}
  purnima:
    label: Purnima
    verified: false
    source: {text: "Dharmasindhu", locus: null}
    rules:
      all: {tithis: [15], anchor: sunrise, start_minutes: 0, end_minutes: 0, on_kshaya: start_day, on_vriddhi: first}
  amavasya:
    label: Amavasya
    verified: false
    source: {text: "Dharmasindhu", locus: null}
    rules:
      all: {tithis: [30], anchor: sunrise, start_minutes: 0, end_minutes: 0, on_kshaya: start_day, on_vriddhi: first}
```

- [ ] **Step 4: Implement `samay/engine/panchang_profile.py`**

```python
"""The family's panchang conventions: one YAML file, validated on load."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .daylight import HORIZON_DEGREES
from .ephemeris import AYANAMSAS
from .errors import UnknownProfile
from .observances import ANCHORS, KSHAYA_CHOICES, VRIDDHI_CHOICES, Rule, Viddha
from .paths import PROFILES_DIR

DEFAULT_PANCHANG_PROFILE = "panchang-family"
SAMPRADAYAS = (None, "smarta", "madhva", "vaishnava")


@dataclass(frozen=True)
class ObservanceSpec:
    name: str
    label: str
    rules: dict[str, Rule]  # tradition name -> rule, or just "all"
    verified: bool  # False: the bot makes no day claim from these rules
    source: dict


@dataclass(frozen=True)
class PanchangProfile:
    id: str
    sampradaya: str | None
    ayanamsa: str
    sunrise_definition: str
    margin_minutes: int
    observances: dict[str, ObservanceSpec]
    sha256: str


def _check(field: str, value: object, allowed) -> None:
    if value not in allowed:
        raise ValueError(f"profile field {field!r}: unsupported value {value!r}")


def _rule(where: str, raw: dict) -> Rule:
    tithis = tuple(int(t) for t in raw["tithis"])
    if not tithis or not all(1 <= t <= 30 for t in tithis):
        raise ValueError(f"{where}: tithis must be numbers 1-30")
    _check(f"{where} anchor", raw["anchor"], ANCHORS)
    _check(f"{where} on_kshaya", raw.get("on_kshaya", "start_day"), KSHAYA_CHOICES)
    _check(f"{where} on_vriddhi", raw.get("on_vriddhi", "first"), VRIDDHI_CHOICES)
    start, end = int(raw["start_minutes"]), int(raw["end_minutes"])
    if start > end:
        raise ValueError(f"{where}: start_minutes is after end_minutes")
    v = raw.get("viddha")
    viddha = None if v is None else Viddha(tuple(int(t) for t in v["tithis"]), v["anchor"], int(v["start_minutes"]), int(v["end_minutes"]))
    if viddha is not None:
        _check(f"{where} viddha anchor", viddha.anchor, ANCHORS)
    return Rule(tithis, raw["anchor"], start, end, raw.get("on_kshaya", "start_day"), raw.get("on_vriddhi", "first"), viddha)


@lru_cache(maxsize=4)
def load_panchang_profile(profile_id: str = DEFAULT_PANCHANG_PROFILE, directory: Path = PROFILES_DIR) -> PanchangProfile:
    path = directory / f"{profile_id}.yaml"
    if not path.is_file():
        raise UnknownProfile(f"unknown panchang profile {profile_id!r}")
    raw_bytes = path.read_bytes()
    raw = yaml.safe_load(raw_bytes)
    _check("sampradaya", raw.get("sampradaya"), SAMPRADAYAS)
    _check("ayanamsa", raw["ayanamsa"], set(AYANAMSAS))
    _check("sunrise_definition", raw["sunrise_definition"], set(HORIZON_DEGREES))
    margin = int(raw["ambiguity_margin_minutes"])
    if margin < 0:
        raise ValueError("profile field 'ambiguity_margin_minutes' must not be negative")
    observances = {}
    for name, spec in raw["observances"].items():
        rules = {who: _rule(f"{name}.{who}", r) for who, r in spec["rules"].items()}
        observances[name] = ObservanceSpec(name, spec["label"], rules, bool(spec["verified"]), spec["source"])
    return PanchangProfile(raw["id"], raw.get("sampradaya"), raw["ayanamsa"], raw["sunrise_definition"], margin,
                           observances, hashlib.sha256(raw_bytes).hexdigest()[:12])
```

- [ ] **Step 5: Run, expect PASS.** `uv run pytest tests/test_panchang_profile.py tests/test_profiles.py -q`

- [ ] **Step 6: Commit.** `git add data/profiles/panchang-family.yaml samay/engine/panchang_profile.py tests/test_panchang_profile.py && git commit -m "feat: panchang profile with per-observance rules, no default tradition"`

---

## Task 6: Tulu month and day

**Files:** Create `samay/engine/tulu.py`, `data/profiles/tulu.yaml`. Test: `tests/test_tulu.py`.

- [ ] **Step 1: Create `data/profiles/tulu.yaml`**

```yaml
# Tulu (Tulunadu) solar calendar. The month is the Sun's sidereal sign; which civil day is day 1 is a disputed choice.
# sankranti_cutoff: same_day | sunset | aparahna | next_day. PROVISIONAL: Task 0 anchors from the family's calendar decide it.
id: tulu
name: Tulu solar calendar
ayanamsa: lahiri_mean
sankranti_cutoff: sunset
source: {text: "Tulu calendar (sauramana); reference app Tulu Panchanga (Apache-2.0)", locus: null, verified: false}
```

- [ ] **Step 2: Write the failing tests** (`tests/test_tulu.py`)

```python
from datetime import date
from pathlib import Path

import pytest
import yaml

from samay.engine import tulu
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
MANGALURU = (12.9141, 74.8560, "Asia/Kolkata")


def at(day, cutoff="sunset"):
    return tulu.tulu_date(day, *MANGALURU, cutoff)


def test_bisu_2026_is_paggu_1_on_14_april():
    t = at(date(2026, 4, 14))
    assert (t.month, t.day) == ("Paggu", 1)
    assert t.ingress.strftime("%d %b") == "14 Apr"


def test_the_day_before_is_the_last_day_of_the_previous_month():
    t = at(date(2026, 4, 13))
    assert t.month == "Suggi" and t.day >= 29


def test_next_day_cutoff_moves_every_month_start_by_one_civil_day():
    assert (at(date(2026, 4, 14), "next_day").month, at(date(2026, 4, 14), "next_day").day) == ("Suggi", 30)
    assert at(date(2026, 4, 15), "next_day").month == "Paggu" and at(date(2026, 4, 15), "next_day").day == 1


def test_an_ingress_after_sunset_starts_the_month_the_next_civil_day():
    # The Sun entered Vrischika on 16 Nov 2026 at about 19:40 local, after sunset.
    assert (at(date(2026, 11, 16)).month, at(date(2026, 11, 17)).month) == ("Bonthel", "Jarde")
    assert at(date(2026, 11, 17)).day == 1 and at(date(2026, 11, 21)).day == 5


def test_pattanaje_is_besha_10():
    assert (at(date(2026, 5, 24)).month, at(date(2026, 5, 24)).day) == ("Besha", 10)


def test_twelve_month_names_in_order():
    assert tulu.MONTHS[0] == "Paggu" and tulu.MONTHS[11] == "Suggi" and len(tulu.MONTHS) == 12


def test_unknown_cutoff_is_rejected():
    with pytest.raises(ValueError, match="cutoff"):
        tulu.tulu_date(date(2026, 4, 14), *MANGALURU, "teatime")


ANCHORS = Path(__file__).parent / "fixtures" / "tulu_anchors.yaml"


@pytest.mark.skipif(not ANCHORS.exists(), reason="family anchors not collected yet (plan Task 0)")
def test_every_family_anchor_matches_under_the_profile_cutoff():
    data = yaml.safe_load(ANCHORS.read_text())
    place = data["place"]
    cutoff = tulu.load_tulu_profile().cutoff
    for a in data["anchors"]:
        t = tulu.tulu_date(a["date"], place["latitude"], place["longitude"], place["tz"], cutoff)
        assert (t.month, t.day) == (a["month"], a["day"]), a
```

- [ ] **Step 3: Run, expect FAIL** (`ImportError: cannot import name 'tulu'`). `uv run pytest tests/test_tulu.py -q`

- [ ] **Step 4: Implement `samay/engine/tulu.py`**

```python
"""The Tulu solar calendar: the month is the Sun's sidereal sign, counted from its entry (sankramana).

Which civil day is day 1 when the Sun enters a sign late in the day is disputed between calendars, so it is a profile
choice (`sankranti_cutoff`), never counted naively: same_day, sunset (before local sunset), aparahna (before 60% of the
daytime has passed) or next_day. The names of these options do not claim a tradition; the family's own anchors decide.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import daylight, ephemeris
from .errors import UnknownProfile
from .paths import PROFILES_DIR

MONTHS = ("Paggu", "Besha", "Kaarthel", "Aati", "Sona", "Nirnala", "Bonthel", "Jarde", "Perarde", "Ponni", "Mayi", "Suggi")
CUTOFFS = ("same_day", "sunset", "aparahna", "next_day")
APARAHNA_FRACTION = 0.6
LOOKBACK = timedelta(days=33)  # longer than any solar month


@dataclass(frozen=True)
class TuluProfile:
    ayanamsa: str
    cutoff: str


@dataclass(frozen=True)
class TuluDate:
    month: str
    day: int
    ingress: datetime  # when the Sun entered this month's sign, local
    month_starts: date  # the civil day the cutoff rule calls day 1


@lru_cache(maxsize=2)
def load_tulu_profile(directory: Path = PROFILES_DIR) -> TuluProfile:
    path = directory / "tulu.yaml"
    if not path.is_file():
        raise UnknownProfile("missing tulu profile")
    raw = yaml.safe_load(path.read_text())
    if raw["sankranti_cutoff"] not in CUTOFFS:
        raise ValueError(f"profile field 'sankranti_cutoff': unsupported value {raw['sankranti_cutoff']!r}")
    if raw["ayanamsa"] not in ephemeris.AYANAMSAS:
        raise ValueError(f"profile field 'ayanamsa': unsupported value {raw['ayanamsa']!r}")
    return TuluProfile(raw["ayanamsa"], raw["sankranti_cutoff"])


def _sun(utc: datetime, ayanamsa: str) -> float:
    return ephemeris.sidereal_track([utc], ayanamsa)["sun"][0]


def last_ingress(utc: datetime, ayanamsa: str = "lahiri_mean") -> tuple[int, datetime]:
    """(sign index 0-11, UTC instant) of the most recent time the Sun entered the sidereal sign it is in at `utc`."""
    sign = int(_sun(utc, ayanamsa) // 30) % 12
    target = sign * 30.0

    def reached(t: datetime) -> bool:
        return (((_sun(t, ayanamsa) - target) + 180.0) % 360.0) - 180.0 >= 0.0

    inside, outside = utc, utc - LOOKBACK  # reached(inside) is True, reached(outside) is False
    while inside - outside > timedelta(seconds=1):
        mid = outside + (inside - outside) / 2
        if reached(mid):
            inside = mid
        else:
            outside = mid
    return sign, inside


def month_start(ingress: datetime, latitude: float, longitude: float, tz: str, cutoff: str) -> date:
    """The civil day that counts as day 1 of the month the Sun entered at `ingress`."""
    local = ingress.astimezone(ZoneInfo(tz))
    day = local.date()
    if cutoff == "same_day":
        return day
    if cutoff == "next_day":
        return day + timedelta(days=1)
    sun = daylight.sun_times(latitude, longitude, tz, day)
    if sun is None:
        return day
    limit = sun.sunset if cutoff == "sunset" else sun.sunrise + (sun.sunset - sun.sunrise) * APARAHNA_FRACTION
    return day if local < limit else day + timedelta(days=1)


def tulu_date(day: date, latitude: float, longitude: float, tz: str, cutoff: str, ayanamsa: str = "lahiri_mean") -> TuluDate:
    if cutoff not in CUTOFFS:
        raise ValueError(f"unknown sankranti cutoff {cutoff!r}")
    zone = ZoneInfo(tz)
    day_end = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(UTC) + timedelta(days=1)
    sign, ingress = last_ingress(day_end - timedelta(seconds=1), ayanamsa)
    start = month_start(ingress, latitude, longitude, tz, cutoff)
    if start > day:  # the Sun entered the sign today but the cutoff makes the month start tomorrow
        sign, ingress = last_ingress(ingress - timedelta(seconds=1), ayanamsa)
        start = month_start(ingress, latitude, longitude, tz, cutoff)
    return TuluDate(MONTHS[sign], (day - start).days + 1, ingress.astimezone(zone), start)
```

- [ ] **Step 5: Run, expect PASS.** `uv run pytest tests/test_tulu.py -q`. (`test_the_day_before...` needs the previous month's length; if `Suggi` day is 30 or 31 the `>= 29` assertion holds.)

- [ ] **Step 6: Commit.** `git add samay/engine/tulu.py data/profiles/tulu.yaml tests/test_tulu.py && git commit -m "feat: Tulu month and day with a profile-chosen sankranti cutoff"`

---

## Task 7: Calculation verification against an independent computation

Geocentric tithi, nakshatra, karana and yoga boundaries are checked against Swiss Ephemeris (the Moshier theory, which needs no data files). This is a development tool only: `pyswisseph` is AGPL, so it is never a runtime dependency and the generated JSON is the only artifact kept, as with `tests/fixtures/golden_suntimes.json`.

**Files:** Create `scripts/golden_panchang.py`, `tests/fixtures/golden_panchang.json`, `tests/test_panchang_golden.py`.

- [ ] **Step 1: Create `scripts/golden_panchang.py`**

```python
"""Regenerate tests/fixtures/golden_panchang.json from Swiss Ephemeris (Moshier theory, no data files needed).

Dev tool only: `uv run --with pyswisseph python scripts/golden_panchang.py`. pyswisseph is AGPL, so it is never a
runtime dependency; only the JSON it writes is kept. Independent of samay's own search code on purpose.
"""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import swisseph as swe

swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
FLAGS = swe.FLG_SIDEREAL | swe.FLG_MOSEPH
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_panchang.json"
CASES = [
    "1985-03-07T01:00", "1999-12-31T06:00", "2000-01-01T00:00", "2010-06-21T05:30", "2015-09-28T02:15",
    "2019-02-04T23:50", "2022-10-25T13:00", "2023-07-04T00:10", "2024-04-08T18:00", "2025-11-05T02:00",
    "2026-03-14T01:00", "2026-04-14T00:43", "2026-11-20T01:13", "2026-11-21T01:14", "2027-01-15T06:30",
    "2030-08-01T03:00", "2040-12-25T11:11",
]


def lon(body: int, t: datetime) -> float:
    jd = swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600 + t.microsecond / 3.6e9)
    return swe.calc_ut(jd, body, FLAGS)[0][0] % 360.0


def sun_moon(t: datetime) -> tuple[float, float]:
    return lon(swe.SUN, t), lon(swe.MOON, t)


QUANT = {
    "tithi": (lambda s, m: (m - s) % 360.0, 12.0),
    "karana": (lambda s, m: (m - s) % 360.0, 6.0),
    "nakshatra": (lambda s, m: m, 360.0 / 27.0),
    "yoga": (lambda s, m: (s + m) % 360.0, 360.0 / 27.0),
}


def cell(kind: str, t: datetime) -> int:
    angle, width = QUANT[kind]
    return int(angle(*sun_moon(t)) // width)


def edge(kind: str, t0: datetime, forward: bool) -> datetime:
    base, sign = cell(kind, t0), 1 if forward else -1
    inside, outside = t0, None
    for hours in range(1, 60):
        probe = t0 + sign * timedelta(hours=hours)
        if cell(kind, probe) != base:
            outside = probe
            break
        inside = probe
    assert outside is not None
    while abs(outside - inside) > timedelta(milliseconds=500):
        mid = inside + (outside - inside) / 2
        if cell(kind, mid) == base:
            inside = mid
        else:
            outside = mid
    return outside if forward else inside


def main() -> None:
    cases = []
    for text in CASES:
        t = datetime.fromisoformat(text).replace(tzinfo=UTC)
        entry = {"instant": t.isoformat()}
        for kind in QUANT:
            entry[kind] = {"number": cell(kind, t) + 1, "start": edge(kind, t, False).isoformat(), "end": edge(kind, t, True).isoformat()}
        cases.append(entry)
    OUT.write_text(json.dumps({"source": "Swiss Ephemeris (Moshier), Lahiri sidereal, geocentric", "cases": cases}, indent=1))
    print(f"wrote {OUT} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the fixture.** `uv run --with pyswisseph python scripts/golden_panchang.py` → `wrote .../golden_panchang.json (17 cases)`.

- [ ] **Step 3: Write the test** (`tests/test_panchang_golden.py`)

```python
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from samay.engine import panchang
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
CASES = json.loads((Path(__file__).parent / "fixtures" / "golden_panchang.json").read_text())["cases"]
TOLERANCE = timedelta(minutes=1)  # Moon moves about 30 arcseconds a minute; Skyfield and Swiss Ephemeris agree far inside this


@pytest.mark.parametrize("case", CASES, ids=[c["instant"] for c in CASES])
@pytest.mark.parametrize("kind", ["tithi", "nakshatra", "karana", "yoga"])
def test_boundaries_match_swiss_ephemeris_within_a_minute(case, kind):
    ours = panchang.element_at(kind, datetime.fromisoformat(case["instant"]))
    theirs = case[kind]
    assert ours.number == theirs["number"]
    assert abs(ours.start - datetime.fromisoformat(theirs["start"])) <= TOLERANCE
    assert abs(ours.end - datetime.fromisoformat(theirs["end"])) <= TOLERANCE
```

- [ ] **Step 4: Run, expect PASS.** `uv run pytest tests/test_panchang_golden.py -q` (68 cases). If a boundary differs by more than a minute, do not widen `TOLERANCE`: report the case, because it means a real calculation difference (for example ΔT before 1972 is not used here, as all cases are 1985 or later).

- [ ] **Step 5: Commit.** `git add scripts/golden_panchang.py tests/fixtures/golden_panchang.json tests/test_panchang_golden.py && git commit -m "test: tithi, nakshatra, karana and yoga boundaries vs Swiss Ephemeris"`

---

## Task 8: Measure the ambiguity margin

**Files:** Create `scripts/measure_margin.py`. Modify `data/profiles/panchang-family.yaml` (the margin value).

- [ ] **Step 1: Create `scripts/measure_margin.py`**

```python
"""Measure the ambiguity margin N (minutes) from the engine's own sensitivity, never from agreement with almanacs.

N = worst sunrise/sunset shift between the two sunrise definitions + worst shift of a tithi boundary caused by a
1 arcminute error in the Sun-Moon elongation. Rule differences between traditions are not part of N.
Run: uv run python scripts/measure_margin.py
"""
from datetime import UTC, date, datetime, timedelta
from math import ceil

from samay.engine import daylight, ephemeris

PLACES = [(18.5196, 73.8553, "Asia/Kolkata"), (12.9141, 74.8560, "Asia/Kolkata"), (44.953, -93.023, "America/Chicago"),
          (-33.8688, 151.2093, "Australia/Sydney"), (51.5074, -0.1278, "Europe/London"), (40.7128, -74.0060, "America/New_York")]
DAYS = [date(2026, 1, 1) + timedelta(days=10 * i) for i in range(37)]


def sunrise_shift_minutes() -> float:
    worst = 0.0
    for lat, lon, tz in PLACES:
        for day in DAYS:
            a, b = daylight.sun_times(lat, lon, tz, day), daylight.sun_times(lat, lon, tz, day, "disc_centre")
            if a and b:
                worst = max(worst, abs((b.sunrise - a.sunrise).total_seconds()), abs((b.sunset - a.sunset).total_seconds()))
    return worst / 60


def boundary_shift_minutes() -> float:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    times = [start + timedelta(days=d) for d in range(365)] + [start + timedelta(days=d, hours=1) for d in range(365)]
    track = ephemeris.sidereal_track(times)
    elong = [(m - s) % 360.0 for s, m in zip(track["sun"], track["moon"], strict=True)]
    slowest = min(((elong[365 + i] - elong[i]) % 360.0) / 60.0 for i in range(365))  # degrees per minute
    return (1 / 60) / slowest


if __name__ == "__main__":
    sun, tithi = sunrise_shift_minutes(), boundary_shift_minutes()
    print(f"sunrise-definition shift {sun:.2f} min, 1' elongation error shifts a boundary by {tithi:.2f} min")
    print(f"ambiguity_margin_minutes = {ceil(sun + tithi)}")
```

- [ ] **Step 2: Run it.** `uv run python scripts/measure_margin.py` → prints the two components and `ambiguity_margin_minutes = N`.

- [ ] **Step 3: Record the measured value.** In `data/profiles/panchang-family.yaml` replace the provisional line with the printed N and update its comment to `# Measured 2026-11-21 by scripts/measure_margin.py (sunrise definition X min + 1' elongation Y min).`, using the real numbers printed. Do not tune N afterwards to make any calendar comparison pass.

- [ ] **Step 4: Run tests.** `uv run pytest tests/test_panchang_profile.py tests/test_observances.py -q` → PASS.

- [ ] **Step 5: Commit.** `git add scripts/measure_margin.py data/profiles/panchang-family.yaml && git commit -m "feat: measure the ambiguity margin from engine sensitivity"`

---

## Task 9: Service layer: reports and the reference place

**Files:** Modify `samay/models.py` (append), `samay/service.py` (append). Test: `tests/test_panchang_service.py`.

- [ ] **Step 1: Add the report types** (append to `samay/models.py`; add `from datetime import date` to its imports if missing)

```python
@dataclass(frozen=True)
class ObservanceDay:
    """An observance the rules name for a day: the label, the primary day, any alternates, and its checked explanation."""
    name: str
    label: str
    primary: date | None
    kind: str  # single | kshaya | vriddhi
    alternates: tuple[tuple[date, str], ...]
    explanation: str | None  # a checked entry's own words, or None


@dataclass(frozen=True)
class PanchangReport:
    place_label: str
    tz: str
    facts: object  # panchang.DayFacts
    tulu: object  # tulu.TuluDate
    cutoff: str  # the Tulu day-1 rule used
    observances: tuple[ObservanceDay, ...]  # only observances whose rules are verified and that touch this day
    needs_sampradaya: bool  # True when day claims were withheld because the family's tradition is not set
    claims_withheld: bool  # True when some observance rules are not verified yet


@dataclass(frozen=True)
class NextObservanceReport:
    place_label: str
    tz: str
    name: str
    label: str
    found: ObservanceDay | None
    claim_available: bool  # False when the rule is unverified or the tradition is not set
    needs_sampradaya: bool
```

- [ ] **Step 2: Write the failing tests** (`tests/test_panchang_service.py`)

```python
from datetime import UTC, date, datetime

import pytest

from samay import service
from samay.engine import entries, panchang_profile
from samay.engine.geo import Place
from samay.engine.paths import EPHEMERIS_PATH

pytestmark = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE = Place("pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458)


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    """A copy of the panchang profile that tests may edit; the service reads it through this directory."""
    import yaml

    from samay.engine.paths import PROFILES_DIR

    for name in ("panchang-family.yaml", "tulu.yaml"):
        (tmp_path / name).write_text((PROFILES_DIR / name).read_text())
    monkeypatch.setattr(service, "PANCHANG_PROFILES_DIR", tmp_path)
    panchang_profile.load_panchang_profile.cache_clear()

    def edit(**top):
        raw = yaml.safe_load((tmp_path / "panchang-family.yaml").read_text())
        raw.update(top)
        (tmp_path / "panchang-family.yaml").write_text(yaml.safe_dump(raw))
        panchang_profile.load_panchang_profile.cache_clear()

    return edit


def test_report_has_local_facts_and_the_tulu_date():
    r = service.panchang_report(PUNE, date(2026, 11, 21))
    assert r.facts.tithi.name == "Shukla Dwadashi" and r.facts.sunrise.strftime("%H:%M") == "06:44"
    assert (r.tulu.month, r.tulu.day) == ("Jarde", 5)


def test_unverified_rules_make_no_day_claim_and_say_so():
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert r.observances == () and r.claims_withheld


def test_a_verified_rule_with_no_tradition_asks_for_one(profile_dir):
    import yaml

    raw = yaml.safe_load((service.PANCHANG_PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["ekadashi"]["verified"] = True
    profile_dir(observances=raw["observances"])
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    assert r.needs_sampradaya and r.observances == ()


def test_a_verified_rule_and_a_set_tradition_name_the_day_with_its_alternate(profile_dir):
    import yaml

    raw = yaml.safe_load((service.PANCHANG_PROFILES_DIR / "panchang-family.yaml").read_text())
    raw["observances"]["ekadashi"]["verified"] = True
    profile_dir(observances=raw["observances"], sampradaya="smarta")
    r = service.panchang_report(PUNE, date(2026, 11, 20))
    (o,) = [x for x in r.observances if x.name == "ekadashi"]
    assert o.primary == date(2026, 11, 20) and o.kind == "kshaya"
    assert (date(2026, 11, 21), "kshaya") in o.alternates
    assert o.explanation is None  # no checked explanation exists yet


def test_next_observance_reports_why_it_cannot_name_a_day():
    n = service.next_observance_report(PUNE, "ekadashi", date(2026, 11, 6))
    assert n.found is None and not n.claim_available


def test_reference_place_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("SAMAY_REFERENCE_PLACE", raising=False)
    assert service.reference_place() is None
    monkeypatch.setenv("SAMAY_REFERENCE_PLACE", "Pune, IN")
    assert service.reference_place().name == "Pune"


def test_explanations_are_only_those_of_checked_entries(tmp_path):
    assert service.observance_explanation("bharani", directory=tmp_path) == []
```

(The last test needs an empty entries directory, so a tmp path with no YAML returns an empty list.)

- [ ] **Step 3: Run, expect FAIL** (`AttributeError: module 'samay.service' has no attribute 'panchang_report'`). `uv run pytest tests/test_panchang_service.py -q`

- [ ] **Step 4: Implement** (append to `samay/service.py`; add the imports `import os`, `from datetime import date, timedelta` if missing, `from .engine import observances, panchang, panchang_profile, tulu`, `from .engine.errors import SampradayaNotSet`, `from .engine.paths import PROFILES_DIR`, and `from .models import NextObservanceReport, ObservanceDay, PanchangReport`)

```python
PANCHANG_PROFILES_DIR = PROFILES_DIR  # a test may point this at a copy


def _panchang_profile() -> panchang_profile.PanchangProfile:
    return panchang_profile.load_panchang_profile(directory=PANCHANG_PROFILES_DIR)


def _site(place: Place) -> panchang.Site:
    return panchang.Site(place.latitude, place.longitude, place.tz)


def reference_place() -> Place | None:
    """The family's reference place (SAMAY_REFERENCE_PLACE, for example "Mangaluru, IN"), separate from a chat's saved home."""
    text = os.environ.get("SAMAY_REFERENCE_PLACE", "").strip()
    if not text:
        return None
    found = geo.find_places(text, limit=1)
    return found[0] if found else None


def observance_explanation(name: str, directory=None) -> list[str]:
    """Checked entries for an observance or nakshatra, in our own words. Unchecked entries are never returned."""
    topic = f"nakshatra:{name}" if name in ("bharani", "krittika") else f"observance:{name}"
    return [e.english for e in entries.answers_for(topic, directory=directory)]


def _explanation(name: str) -> str | None:
    found = observance_explanation(name)
    return found[0] if found else None


def _as_day(name: str, label: str, o: observances.Observance) -> ObservanceDay:
    return ObservanceDay(name, label, o.primary, o.kind, tuple((a.day, a.reason) for a in o.alternates), _explanation(name))


def panchang_report(place: Place, day: date) -> PanchangReport | None:
    """Everything the bot says about one local day at a place. Observance days are named only from verified rules
    and only once the family's tradition is set; otherwise the report says that a claim was withheld."""
    profile, site = _panchang_profile(), _site(place)
    facts = panchang.day_facts(site, day, profile.ayanamsa, profile.sunrise_definition)
    if facts is None:
        return None
    tulu_profile = tulu.load_tulu_profile(PANCHANG_PROFILES_DIR)
    date_in_tulu = tulu.tulu_date(day, place.latitude, place.longitude, place.tz, tulu_profile.cutoff, tulu_profile.ayanamsa)
    today, needs_tradition, withheld = [], False, False
    for spec in profile.observances.values():
        if not spec.verified:
            withheld = True
            continue
        try:
            found = observances.observances_for(spec.rules, profile.sampradaya, site, day, day, profile.ayanamsa,
                                                profile.margin_minutes, profile.sunrise_definition)
        except SampradayaNotSet:
            needs_tradition = True
            continue
        today += [_as_day(spec.name, spec.label, o) for o in found]
    return PanchangReport(place.label, place.tz, facts, date_in_tulu, tulu_profile.cutoff, tuple(today), needs_tradition, withheld)


def next_observance_report(place: Place, name: str, today: date) -> NextObservanceReport:
    profile = _panchang_profile()
    spec = profile.observances[name]
    base = dict(place_label=place.label, tz=place.tz, name=name, label=spec.label)
    if not spec.verified:
        return NextObservanceReport(**base, found=None, claim_available=False, needs_sampradaya=False)
    try:
        found = observances.find_next(spec.rules, profile.sampradaya, _site(place), today, profile.ayanamsa,
                                      profile.margin_minutes, profile.sunrise_definition)
    except SampradayaNotSet:
        return NextObservanceReport(**base, found=None, claim_available=False, needs_sampradaya=True)
    return NextObservanceReport(**base, found=None if found is None else _as_day(name, spec.label, found),
                                claim_available=True, needs_sampradaya=False)
```

Note `place.label` exists on `geo.Place` (used by `render_rahu_kaala(rahu, place.label)`); if the test's hand-built `Place` lacks it, build it with the same constructor fields the gazetteer uses.

- [ ] **Step 5: Run, expect PASS.** `uv run pytest tests/test_panchang_service.py -q`

- [ ] **Step 6: Add the new engine modules to the warm-up.** In `service.warm()` add, after `_rules(...)`: `_panchang_profile()` and `tulu.load_tulu_profile(PANCHANG_PROFILES_DIR)` so a missing profile stops start-up. Run `uv run pytest tests/test_service.py -q`.

- [ ] **Step 7: Commit.** `git add samay/models.py samay/service.py tests/test_panchang_service.py && git commit -m "feat: service reports for a panchang day and the next observance"`

---

## Task 10: Wording and the plain-language morning message

**Files:** Create `samay/render/panchang.py`. Modify `samay/render/text.py` (`render_brief`) and `samay/bot/app.py` (`compose_brief`, `_brief_job`). Tests: `tests/test_render_panchang.py`, `tests/test_render.py`.

- [ ] **Step 1: Write the failing tests** (`tests/test_render_panchang.py`)

```python
from datetime import date, datetime, timedelta, timezone

from samay.models import NextObservanceReport, ObservanceDay, PanchangReport
from samay.render import panchang as words

IST = timezone(timedelta(hours=5, minutes=30))


class El:
    def __init__(self, name, end):
        self.name, self.end = name, end


class Facts:
    sunrise = datetime(2026, 11, 21, 6, 44, tzinfo=IST)
    sunset = datetime(2026, 11, 21, 17, 56, tzinfo=IST)
    tithi = El("Shukla Dwadashi", datetime(2026, 11, 21, 23, 27, tzinfo=timezone.utc))
    nakshatra = El("Revati", datetime(2026, 11, 22, 0, 24, tzinfo=timezone.utc))
    karana = El("Balava", datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc))
    yoga = El("Siddha", datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc))


class Tulu:
    month, day = "Jarde", 5
    month_starts = date(2026, 11, 17)
    ingress = datetime(2026, 11, 16, 19, 39, tzinfo=IST)


def report(**changes):
    base = dict(place_label="Pune", tz="Asia/Kolkata", facts=Facts, tulu=Tulu, cutoff="sunset", observances=(),
                needs_sampradaya=False, claims_withheld=True)
    base.update(changes)
    return PanchangReport(**base)


def test_day_answer_uses_plain_words_and_local_times():
    text = words.render_day(report(), date(2026, 11, 21))
    assert "Saturday, 21 November 2026" in text and "Pune" in text
    assert "Shukla Dwadashi" in text and "Revati" in text and "06:44" in text and "17:56" in text
    assert "Tulu date: Jarde 5" in text and "sunset rule" in text
    assert "Rahu" not in text and "mahadasha" not in text.lower()


def test_unverified_rules_say_plainly_that_no_observance_day_is_named():
    assert "not named" in words.render_day(report(), date(2026, 11, 21)).lower()


def test_missing_tradition_asks_for_it():
    assert "tradition" in words.render_day(report(needs_sampradaya=True), date(2026, 11, 21)).lower()


def test_an_observance_day_shows_its_alternate_and_a_local_panchang_note():
    o = ObservanceDay("ekadashi", "Ekadashi", date(2026, 11, 20), "kshaya", ((date(2026, 11, 21), "kshaya"),), None)
    text = words.render_day(report(observances=(o,), claims_withheld=False), date(2026, 11, 20))
    assert "Ekadashi" in text and "21 November" in text and "local panchang may differ" in text


def test_a_checked_explanation_is_included_in_our_own_words():
    o = ObservanceDay("ekadashi", "Ekadashi", date(2026, 11, 20), "single", (), "A day many households fast.")
    assert "A day many households fast." in words.render_day(report(observances=(o,), claims_withheld=False), date(2026, 11, 20))


def test_next_answer_cases():
    found = ObservanceDay("ekadashi", "Ekadashi", date(2026, 11, 20), "single", (), None)
    ok = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", found, True, False)
    assert "Friday, 20 November 2026" in words.render_next(ok)
    unverified = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", None, False, False)
    assert "not set up" in words.render_next(unverified)
    needs = NextObservanceReport("Pune", "Asia/Kolkata", "ekadashi", "Ekadashi", None, False, True)
    assert "tradition" in words.render_next(needs)


def test_about_answer_without_a_checked_entry_is_honest():
    assert "no checked source" in words.render_about("Ekadashi", []).lower()
    assert "Our own words." in words.render_about("Bharani", ["Our own words."])


def test_brief_is_plain_language_with_no_dasha_and_no_jargon():
    text = words.render_brief(datetime(2026, 11, 21, 7, 0), None, "Pune", report())
    assert text.startswith("🌅 Good morning! Today is Saturday, 21 November 2026.")
    assert "Tulu date: Jarde 5" in text
    assert "dasha" not in text.lower() and "Rahu Kaala" not in text
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: samay.render.panchang`). `uv run pytest tests/test_render_panchang.py -q`

- [ ] **Step 3: Implement `samay/render/panchang.py`**

```python
"""All wording for panchang answers and the morning message. Facts only: no predictions, no outcomes."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..models import NextObservanceReport, ObservanceDay, PanchangReport

NOTE_LOCAL = "A local panchang may differ, because traditions count this day differently."
NO_CLAIM = "Observance days are not named yet: the rules for them are not set up from a checked source."
NEED_TRADITION = "To name observance days I need to know which tradition your family follows. Please set it first."
TOO_FAR = "I can only work out days between 1972 and 2150."
NO_SUN = "The Sun does not both rise and set that day in {place}, so I cannot give sunrise-based times."


def _day(d: date) -> str:
    return f"{d:%A, %d %B %Y}"


def _clock(moment: datetime, tz: str, day: date | None = None) -> str:
    local = moment.astimezone(ZoneInfo(tz))
    return f"{local:%H:%M}" if day is None or local.date() == day else f"{local:%H:%M} on {local:%d %b}"


def _until(element, tz: str, day: date) -> str:
    return f"until {_clock(element.end, tz, day)}"


def _observance_lines(o: ObservanceDay, day: date | None = None) -> list[str]:
    if o.primary is None:
        return [f"{o.label}: the rule I use gives no clear day for this one. {NOTE_LOCAL}"]
    when = "today" if day is not None and o.primary == day else _day(o.primary)
    lines = [f"{o.label}: {when}."]
    others = [d for d, _ in o.alternates]
    if others:
        lines.append(f"Some calendars place it on {', '.join(_day(d) for d in others)}. {NOTE_LOCAL}")
    if o.explanation:
        lines.append(o.explanation)
    return lines


def render_day(report: PanchangReport, day: date) -> str:
    f, tz = report.facts, report.tz
    lines = [f"{_day(day)} in {report.place_label}",
             f"Tithi (the Moon's lunar day): {f.tithi.name}, {_until(f.tithi, tz, day)}.",
             f"Nakshatra (the Moon's star): {f.nakshatra.name}, {_until(f.nakshatra, tz, day)}.",
             f"Karana: {f.karana.name}. Yoga: {f.yoga.name}.",
             f"Sunrise {_clock(f.sunrise, tz)}, sunset {_clock(f.sunset, tz)}.",
             f"Tulu date: {report.tulu.month} {report.tulu.day} (the month began {report.tulu.month_starts:%d %b}; "
             f"worked out by the {report.cutoff.replace('_', ' ')} rule)."]
    for o in report.observances:
        lines += _observance_lines(o, day)
    if report.needs_sampradaya:
        lines.append(NEED_TRADITION)
    elif report.claims_withheld and not report.observances:
        lines.append(NO_CLAIM)
    return "\n".join(lines)


def render_next(report: NextObservanceReport) -> str:
    if report.needs_sampradaya:
        return NEED_TRADITION
    if not report.claim_available:
        return f"The day for {report.label} is not set up from a checked source yet, so I will not name one."
    if report.found is None:
        return f"I could not find the next {report.label} in the coming weeks."
    return "\n".join([f"The next {report.label} is {_day(report.found.primary)} in {report.place_label}."]
                     + _observance_lines(report.found)[1:])


def render_about(label: str, explanations: list[str]) -> str:
    if not explanations:
        return f"I have no checked source for {label} yet, so I will not describe what it means."
    return "\n\n".join(explanations)


def render_avoid_window(rahu, place_label: str) -> str:
    if rahu is None:
        return f"The Sun does not both rise and set today in {place_label}, so there is no usual avoid-window."
    return (f"Traditionally avoided for starting new things: {rahu.start:%H:%M} to {rahu.end:%H:%M} "
            f"(called Rahu Kaala), {place_label}.")


def render_brief(local_now: datetime, rahu, place_label: str, report: PanchangReport | None) -> str:
    lines = [f"🌅 Good morning! Today is {_day(local_now.date())}.", render_avoid_window(rahu, place_label)]
    if report is not None:
        f, tz = report.facts, report.tz
        lines.append(f"Today: {f.tithi.name}, with the Moon in {f.nakshatra.name}.")
        for o in report.observances:
            lines += _observance_lines(o, local_now.date())
        lines.append(f"Tulu date: {report.tulu.month} {report.tulu.day}.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, expect PASS.** `uv run pytest tests/test_render_panchang.py -q`

- [ ] **Step 5: Delegate the old brief to the new wording.** In `samay/render/text.py` replace the body of `render_brief` with a re-export, keeping the old import path working:

```python
def render_brief(local_now, rahu, place_label, report):
    """The morning message, in plain words. The dasha line was dropped: it implied a meaning without giving one."""
    from .panchang import render_brief as plain

    return plain(local_now, rahu, place_label, report)
```

- [ ] **Step 6: Update the old test.** In `tests/test_render.py` replace `test_brief_has_date_rahu_kaala_and_dasha_dates_but_no_meanings` with:

```python
def test_brief_is_plain_and_has_no_dasha_line():
    from datetime import date

    from samay.engine import daylight
    from samay.render.text import render_brief

    rahu = daylight.rahu_kaala(18.5196, 73.8553, "Asia/Kolkata", date(2026, 11, 9))
    text = render_brief(datetime(2026, 11, 9, 7, 0), rahu, "Pune", None)
    assert text.splitlines()[0] == "🌅 Good morning! Today is Monday, 09 November 2026."
    assert "Traditionally avoided for starting new things" in text and "(Pune)" not in text.splitlines()[0]
    assert "dasha" not in text.lower() and len(text.splitlines()) == 2
```

- [ ] **Step 7: Rewire the bot's morning message.** In `samay/bot/app.py` replace `compose_brief`:

```python
def compose_brief(saved: BirthInput | None, place, now: datetime) -> str:
    """The morning message for someone living in `place`. Synchronous; the bot runs it in a thread.
    `saved` is no longer used (the dasha line was dropped) and stays only so callers do not change."""
    local_now = now.astimezone(ZoneInfo(place.tz))
    report = service.panchang_report(place, local_now.date())
    return render_brief(local_now, service.rahu_kaala_for(place, now), place.label, report)
```

- [ ] **Step 8: Run the affected suites and fix wording asserts.** `uv run pytest tests/test_render.py tests/test_render_panchang.py tests/test_bot.py -q`. Any test that asserts the old "Running now:" or "mahadasha" brief text must be updated to the new wording (expected: only the brief tests listed by `grep -n brief tests/test_bot.py`).

- [ ] **Step 9: Update `BRIEF_ASK`** in `samay/render/prompts.py` to match: `"Every morning I can send a short message with today's date, the Moon's day and a time to avoid starting new things.\nAt what time?"`.

- [ ] **Step 10: Commit.** `git add samay/render samay/bot/app.py tests && git commit -m "feat: plain-language morning message with the day's panchang and Tulu date"`

---

## Task 11: Question routing (table-driven) and the bot hook

**Files:** Create `samay/panchang_qa.py`. Modify `samay/bot/app.py` (`_answer_question`). Test: `tests/test_panchang_qa.py`.

Deliberate deviation from the spec's wording: `qa.py` routes birth-chart questions and its `answer_topic` needs a birth, while a panchang answer needs a place and a date. So the hook sits beside it in the bot's `_answer_question` instead of inside `qa.py`, and `qa.py` is left untouched. Update the spec in Task 14.

- [ ] **Step 1: Write the failing tests** (`tests/test_panchang_qa.py`)

```python
from datetime import UTC, date, datetime

import pytest

from samay import panchang_qa as pq
from samay.engine.geo import Place
from samay.engine.paths import EPHEMERIS_PATH

PUNE = Place("pune", "Pune", "IN", "Maharashtra", None, 18.5196, 73.8553, "Asia/Kolkata", 3124458)
TODAY = date(2026, 11, 21)  # a Saturday


@pytest.mark.parametrize("text, kind, observance", [
    ("is today special?", "day", None),
    ("what's the tithi today", "day", None),
    ("is tomorrow auspicious", "day", None),
    ("when is the next Ekadashi?", "next", "ekadashi"),
    ("next pradosh", "next", "pradosha"),
    ("what is Ekadashi", "about", "ekadashi"),
    ("why is Purnima important", "about", "purnima"),
    ("when is amavasya", "next", "amavasya"),
    ("what is the panchang on 2026-12-04", "day", None),
])
def test_questions_are_sorted(text, kind, observance):
    asked = pq.sort(text)
    assert (asked.kind, asked.observance) == (kind, observance)


@pytest.mark.parametrize("text", [
    "what is my nakshatra", "when was I born, what star", "tell me about Jupiter", "will Ekadashi bring me luck?",
    "is tomorrow a good day to buy shares", "hello",
])
def test_everything_else_is_left_to_the_existing_router(text):
    assert pq.sort(text) is None


@pytest.mark.parametrize("text, expected", [
    ("is today special", TODAY), ("is tomorrow auspicious", date(2026, 11, 22)),
    ("tithi on Monday", date(2026, 11, 23)), ("panchang 2026-12-04", date(2026, 12, 4)),
    ("panchang on 4 December 2026", date(2026, 12, 4)),
])
def test_dates_are_resolved_in_the_places_own_day(text, expected):
    assert pq.resolve_when(pq.sort(text).when, TODAY) == expected


pytestmark_engine = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")


@pytestmark_engine
def test_a_day_question_gets_the_facts():
    reply = pq.answer(pq.sort("what is the tithi today"), PUNE, datetime(2026, 11, 21, 4, 0, tzinfo=UTC))
    assert "Shukla Dwadashi" in reply and "Tulu date" in reply


@pytestmark_engine
def test_a_next_question_without_a_verified_rule_does_not_name_a_day():
    reply = pq.answer(pq.sort("when is the next Ekadashi"), PUNE, datetime(2026, 11, 21, 4, 0, tzinfo=UTC))
    assert "not set up" in reply


@pytestmark_engine
def test_an_about_question_without_a_checked_entry_says_so():
    reply = pq.answer(pq.sort("what is Ekadashi"), PUNE, datetime(2026, 11, 21, 4, 0, tzinfo=UTC))
    assert "no checked source" in reply.lower()


@pytestmark_engine
def test_far_future_dates_get_a_plain_refusal():
    reply = pq.answer(pq.sort("panchang on 2300-01-01"), PUNE, datetime(2026, 11, 21, 4, 0, tzinfo=UTC))
    assert "1972 and 2150" in reply
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError`). `uv run pytest tests/test_panchang_qa.py -q`

- [ ] **Step 3: Implement `samay/panchang_qa.py`**

```python
"""Panchang questions: a table-driven sorter and the answer. A new observance is a row in OBSERVANCES, not a new
parsing path. Anything about the person's own chart, about outcomes, or about no panchang word is left to qa.py."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import service
from .engine.errors import OutOfEphemerisRange
from .render import panchang as words

OBSERVANCES = {
    "ekadashi": ("ekadashi", "ekadasi", "ekadashis"),
    "pradosha": ("pradosha", "pradosh", "pradoshas"),
    "purnima": ("purnima", "poornima", "pournami", "fullmoon"),
    "amavasya": ("amavasya", "amavasai", "newmoon"),
}
LABELS = {"ekadashi": "Ekadashi", "pradosha": "Pradosha", "purnima": "Purnima", "amavasya": "Amavasya"}
DAY_WORDS = ("tithi", "panchang", "panchanga", "panchangam")
SPECIAL_WORDS = ("special", "auspicious", "inauspicious", "festival", "fasting", "vrat", "vratam")
NEXT_WORDS = ("when", "next", "upcoming")
ABOUT_WORDS = ("what", "why", "mean", "meaning", "important", "importance", "significance")
PERSONAL_WORDS = ("my", "mine", "born", "birth", "birthday")  # a question about the person's own chart
OUTCOME_WORDS = ("luck", "lucky", "fortune", "bring", "will", "good", "buy", "shares", "profit", "result")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
_WORD = re.compile(r"[a-z]+")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({'|'.join(MONTHS)})\s+(\d{{4}})\b")


@dataclass(frozen=True)
class When:
    kind: str  # today | tomorrow | weekday | date
    value: object = None  # a weekday index or a date


@dataclass(frozen=True)
class Asked:
    kind: str  # day | next | about
    observance: str | None
    when: When


def _when(text: str, words_: list[str]) -> When:
    iso = _ISO.search(text)
    if iso:
        return When("date", date(int(iso[1]), int(iso[2]), int(iso[3])))
    dmy = _DAY_MONTH_YEAR.search(text)
    if dmy:
        return When("date", date(int(dmy[3]), MONTHS.index(dmy[2]) + 1, int(dmy[1])))
    if "tomorrow" in words_:
        return When("tomorrow")
    for i, name in enumerate(WEEKDAYS):
        if name in words_:
            return When("weekday", i)
    return When("today")


def sort(text: str) -> Asked | None:
    lowered = text.casefold()
    found = _WORD.findall(lowered)
    compact = lowered.replace(" ", "")
    if any(w in PERSONAL_WORDS for w in found) or any(w in OUTCOME_WORDS for w in found):
        return None
    observance = next((name for name, aliases in OBSERVANCES.items() if any(a in found or a in compact for a in aliases)), None)
    when = _when(lowered, found)
    if observance:
        if any(w in NEXT_WORDS for w in found):
            return Asked("next", observance, when)
        if any(w in ABOUT_WORDS for w in found):
            return Asked("about", observance, when)
        return Asked("next", observance, when)
    if any(w in DAY_WORDS for w in found) or (any(w in SPECIAL_WORDS for w in found) and when.kind != "today") \
            or (any(w in SPECIAL_WORDS for w in found) and "today" in found):
        return Asked("day", None, when)
    return None


def resolve_when(when: When, today: date) -> date:
    if when.kind == "date":
        return when.value
    if when.kind == "tomorrow":
        return today + timedelta(days=1)
    if when.kind == "weekday":
        return today + timedelta(days=(when.value - today.weekday()) % 7 or 7)
    return today


def answer(asked: Asked, place, now: datetime) -> str:
    today = now.astimezone(ZoneInfo(place.tz)).date()
    try:
        if asked.kind == "about":
            return words.render_about(LABELS[asked.observance], service.observance_explanation(asked.observance))
        if asked.kind == "next":
            return words.render_next(service.next_observance_report(place, asked.observance, today))
        day = resolve_when(asked.when, today)
        if not 1973 <= day.year <= 2149:  # the engine's own range: sidereal positions start in 1972, the kernel ends in 2150
            return words.TOO_FAR
        report = service.panchang_report(place, day)
        return words.NO_SUN.format(place=place.label) if report is None else words.render_day(report, day)
    except OutOfEphemerisRange:
        return words.TOO_FAR
```

- [ ] **Step 4: Run, expect PASS.** `uv run pytest tests/test_panchang_qa.py -q`. Check the sorter table: `"is tomorrow a good day to buy shares"` and `"will Ekadashi bring me luck?"` must return `None` (outcome words), `"what is my nakshatra"` must return `None` (personal word).

- [ ] **Step 5: Hook into the bot.** In `samay/bot/app.py` add `from .. import panchang_qa` to the imports, add this function above `_answer_question`:

```python
async def _answer_panchang(update: Update, ctx, chat_id: int, question: str) -> bool:
    """Panchang questions (today's tithi, the next Ekadashi, what Ekadashi is) need a place, not a birth, so they are
    answered before the birth-chart router. Returns True when it answered."""
    asked = panchang_qa.sort(question)
    if asked is None:
        return False
    place = service.reference_place()
    if place is None:
        home = await asyncio.to_thread(_store(ctx).get_home, chat_id)
        place = geo.get_place(home.place_id) if home is not None else None
    if place is None:
        await _send_flow(update, ctx, chat_id, flow.begin_home(), f"{prompts.NEED_HOME}\n\n")
        return True
    await _say(update, await asyncio.to_thread(panchang_qa.answer, asked, place, _now()), MENU)
    return True
```

and make the first statement inside `_answer_question` (before `ai = narrate.enabled()`):

```python
    if await _answer_panchang(update, ctx, chat_id, question):
        return
```

- [ ] **Step 6: Write a bot test** (append to `tests/test_bot.py`, following the pattern of its existing question tests: copy the setup of the nearest test that sends a text question and asserts on `ctx`/reply, then assert the reply for `"what is the tithi today"` contains `"Tulu date"`, and that `"tell me about Jupiter"` still reaches the old router). Run `uv run pytest tests/test_bot.py -q`.

- [ ] **Step 7: Full suite and commit.** `uv run ruff check && uv run pytest -q` → PASS. `git add samay/panchang_qa.py samay/bot/app.py tests && git commit -m "feat: answer panchang questions in chat"`

---

## Task 12: Checked-entry plumbing and the Bharani and Krittika entries

**Files:** Create `data/entries/panchang-observances.yaml`. Test: `tests/test_panchang_entries.py`.

The passage was read in the Subrahmanya Sastri translation of Brihat Samhita (chapter 98, "On the Functions and Properties of the Asterisms"). The sloka numbers below were read from OCR text and must be confirmed against the page image when the entries are promoted in Task 13. They ship `unchecked`, so nothing is shown until then.

- [ ] **Step 1: Write the failing test** (`tests/test_panchang_entries.py`)

```python
from samay import service
from samay.engine import entries


def test_shipped_panchang_entries_load_and_are_hidden_until_checked():
    found = [e for e in entries.load_entries() if e.id.startswith("panchang-")]
    assert {e.topic for e in found} == {"nakshatra:bharani", "nakshatra:krittika"}
    assert all(e.citation["text"] == "Brihat Samhita" and e.citation["chapter"] == 98 for e in found)
    assert all(not e.servable for e in found)  # unchecked until Task 13
    assert service.observance_explanation("bharani") == []


def test_wording_follows_the_text_and_gives_no_avoid_instruction():
    for e in (e for e in entries.load_entries() if e.id.startswith("panchang-")):
        assert "avoid" not in e.english.lower() and "inauspicious" not in e.english.lower()
```

- [ ] **Step 2: Run, expect FAIL** (no `panchang-` entries). `uv run pytest tests/test_panchang_entries.py -q`

- [ ] **Step 3: Create `data/entries/panchang-observances.yaml`**

```yaml
# Panchang entries. Paraphrased in our own words; read in the Subrahmanya Sastri translation (Bangalore, 1946-47).
# Sloka numbers come from OCR text: confirm against the page image before promoting past `unchecked`.
- id: panchang-bharani-bs98-8
  topic: nakshatra:bharani
  system: any
  english: >-
    The old text puts Bharani among five nakshatras it calls ugra, meaning fierce or dreadful (the others are Magha
    and the three Purvas). It says these suit forceful work: overcoming rivals, destruction, deceit, imprisonment,
    poisoning, setting fires and using weapons. It does not tell anyone to avoid Bharani.
  citation: {text: Brihat Samhita, chapter: 98, verse: "8", edition: "tr. V. Subrahmanya Sastri and M. Ramakrishna Bhat (Bangalore, 1946-47)"}
  verification: {level: unchecked}
- id: panchang-krittika-bs98-11
  topic: nakshatra:krittika
  system: any
  english: >-
    The old text puts Krittika, together with Vishakha, among the nakshatras it calls mixed (tender-sharp), meaning
    results of both kinds. It does not tell anyone to avoid Krittika.
  citation: {text: Brihat Samhita, chapter: 98, verse: "11", edition: "tr. V. Subrahmanya Sastri and M. Ramakrishna Bhat (Bangalore, 1946-47)"}
  verification: {level: unchecked}
```

- [ ] **Step 4: Run the entry tests.** `uv run pytest tests/test_panchang_entries.py tests/test_entries.py -q` → PASS.

- [ ] **Step 5: Show the nakshatra explanation in the day answer.** In `service.panchang_report` nothing changes; in `render/panchang.py::render_day`, after the nakshatra line, add when a checked entry exists. Add a parameter-free hook: `PanchangReport` gets no new field, so instead extend `ObservanceDay` use: in `service.panchang_report` append, after the observance loop,

```python
    nak = facts.nakshatra.name.lower()
    if (note := _explanation(nak)) is not None:
        today.append(ObservanceDay(nak, facts.nakshatra.name, None, "single", (), note))
```

and in `_observance_lines` treat `primary is None and o.explanation` as an explanation-only line: change its first branch to

```python
    if o.primary is None:
        return [o.explanation] if o.explanation else [f"{o.label}: the rule I use gives no clear day for this one. {NOTE_LOCAL}"]
```

Add a test to `tests/test_panchang_service.py` that a checked Revati-like entry from a tmp entries directory is shown (use `monkeypatch.setattr(entries, "ENTRIES_DIR", tmp_path)` and `entries.load_entries.cache_clear()`), and that with no checked entry nothing extra appears. Run `uv run pytest tests/test_panchang_service.py tests/test_render_panchang.py -q`.

- [ ] **Step 6: Commit.** `git add data/entries/panchang-observances.yaml samay tests && git commit -m "feat: Bharani and Krittika entries (hidden until checked) and nakshatra explanations"`

---

## Task 13: Sourcing spike (time-boxed: three sessions)

This turns provisional rules and unchecked entries into verified ones, or leaves them hidden. Nothing here changes code except YAML values and `verified` flags. For each item, record what was read in `research/notes/panchang-sources.md`.

- [ ] **Step 1: Read the day-selection rules.** Read the Kamakoti "Essence of Dharma Sindhu", chapter 3 (`https://www.kamakoti.org/kamakoti/dharmasindhu/bookview.php?chapnum=3`) and find: (a) the sunrise rule for the day of a tithi, (b) the kshaya and vriddhi provisions, (c) the Ekadashi-specific viddha rule and the arunodaya length. Set `on_kshaya`, `on_vriddhi`, the Madhva `viddha` window and `start_minutes`/`end_minutes` in `data/profiles/panchang-family.yaml` to what the text says, fill `locus`, and set `verified: true` for an observance only when its numbers match the passage you read. A rule whose passage cannot be read after the time-box stays `verified: false` (its facts still show; no day is named).
- [ ] **Step 2: Read Pradosha.** Read the Skanda Purana, Brahma Khanda passage on Pradosha (wisdomlib, `https://www.wisdomlib.org/hinduism/book/the-skanda-purana/d/doc423669.html`, verses 5-14 and 74-78) and a digest for the window length. Set the window in the profile and add an entry `observance:pradosha` to `data/entries/panchang-observances.yaml` paraphrasing what the passage says in our own words, citing text, chapter, verse and edition.
- [ ] **Step 3: Read Ekadashi, Purnima, Amavasya.** Read the Hari Bhakti Vilasa, Padma Purana and Dharmasindhu passages named in `research/notes/panchang-sources.md`, and add `observance:ekadashi`, `observance:purnima` and `observance:amavasya` entries only for passages you actually read.
- [ ] **Step 4: Confirm the Bharani and Krittika slokas** (8 and 11) against the page image of the Sastri translation on archive.org (`https://archive.org/details/Brihatsamhita`).
- [ ] **Step 5: Promote.** For each entry you verified set:

```yaml
  verification:
    level: translation-checked
    checked_by: <who read it>
    checked_on: <date>
    against: "<the translation read, with edition>"
```

  Leave everything else `unchecked`.
- [ ] **Step 6: Run** `uv run pytest -q` (the entry and profile tests must still pass; update `test_shipped_panchang_entries_load_and_are_hidden_until_checked` to match which entries are now served, and `test_every_shipped_rule_is_marked_unverified_until_sourced` to the new truth).
- [ ] **Step 7: Commit.** `git add data research tests && git commit -m "docs: source the observance rules and entries that could be read"`

---

## Task 14: Convention verification, known divergences, and wrap-up

Requires Task 0's `tests/fixtures/family_panchang_dates.yaml`. If it does not exist yet, the test below skips with that reason and this task stays open.

**Files:** Create `tests/test_panchang_convention.py`. Modify the spec.

- [ ] **Step 1: Write the test** (`tests/test_panchang_convention.py`)

```python
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from samay.engine import observances, panchang_profile
from samay.engine.panchang import Site
from samay.engine.paths import EPHEMERIS_PATH

FIXTURE = Path(__file__).parent / "fixtures" / "family_panchang_dates.yaml"
pytestmark = [pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present"),
              pytest.mark.skipif(not FIXTURE.exists(), reason="family dates not collected yet (plan Task 0)")]


def test_engine_agrees_with_the_family_calendar_or_every_difference_is_explained():
    data = yaml.safe_load(FIXTURE.read_text())
    profile = panchang_profile.load_panchang_profile()
    place = data["place"]
    site = Site(place["latitude"], place["longitude"], place["tz"])
    listed = {(d["observance"], d["date"]) for d in data["dates"]}
    explained = {(d["observance"], d["date"]) for d in data["known_divergences"]}
    first, last = min(d for _, d in listed), max(d for _, d in listed)
    problems = []
    for name in {n for n, _ in listed}:
        spec = profile.observances[name]
        ours = {o.primary for o in observances.observances_for(spec.rules, data["sampradaya"], site, first, last + timedelta(days=1),
                                                               profile.ayanamsa, profile.margin_minutes, profile.sunrise_definition)
                if o.primary is not None}
        for day in sorted(ours | {d for n, d in listed if n == name}):
            if first <= day <= last and ((name, day) in listed) != (day in ours) and (name, day) not in explained:
                problems.append((name, day.isoformat(), "engine" if day in ours else "calendar"))
    assert not problems, f"unexplained differences (name, date, who has it): {problems}"
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_panchang_convention.py -q`. Each failure is either a real bug (fix the engine) or a convention difference: add it to `known_divergences` with a `cause` naming the convention. Do not change the margin or any rule only to make a date match.
- [ ] **Step 3: Reconcile the spec.** In `docs/superpowers/specs/2026-11-21-panchang-core-design.md` section 6, change "`qa.py` stays thin ... `qa.py` calls it" to say the hook sits in the bot's `_answer_question` beside `qa.py`, which is untouched, and why (a panchang answer needs a place and a date, not a birth).
- [ ] **Step 4: Full verification.** `uv run ruff check && uv run pytest -q` → all pass. Confirm `data/de440s.bsp` exists so the engine tests did not skip (`uv run pytest -q -rs | grep -c "ephemeris file not present"` → `0`).
- [ ] **Step 5: Run the app once** and ask it: "what is the tithi today", "when is the next Ekadashi", "what is Ekadashi" (`SAMAY_REFERENCE_PLACE="Mangaluru, IN"`), and check the morning message through `compose_brief`. Report exactly what it said; if a verified rule is missing, the next-Ekadashi answer must say it is not set up.
- [ ] **Step 6: Commit.** `git add tests docs && git commit -m "test: engine vs the family calendar with explained divergences; reconcile the spec"`

---

## Self-review against the spec

- **Spec 2 scope.** Elements and day facts: Tasks 2-3. Per-observance rules, primary plus alternate, kshaya/vriddhi: Task 4. Tulu month and day: Task 6. Chat Q&A: Task 11. Plain-language brief: Task 10. All covered.
- **Spec 3 decisions.** Local sunrise and timezone: Tasks 1, 3 (DST and southern tests). No default tradition: Tasks 4-5, 9. Margin measured, calculation only: Task 8. Window primitive: Task 4. Reference place separate from home: Task 9.
- **Spec 4-5.** Engine takes a site and a date: Tasks 2-4. Reference location layer: Task 9.
- **Spec 6, 6a, 6b.** Table-driven routing: Task 11 (with the documented hook-location deviation). Model context limited to checked entries: no new model path is added; `service.observance_explanation` returns only `answers_for` results, which exclude unchecked entries, so any model reword sees only those. The dasha line is dropped: Task 10.
- **Spec 7.** Explanations are a non-blocking track: Tasks 12-13. Bharani and Krittika wording follows the text and the test forbids "avoid": Task 12.
- **Spec 8.** Calculation layer: Task 7 (within a minute, 17 instants). Margin from sensitivity: Task 8. Convention layer with known divergences: Task 14. Kshaya is in the fixtures through the Pune 20-21 Nov 2026 test (Task 4); vriddhi through the wide-window test.
- **Spec 9 gate 0.** Task 0.
- **Known gaps, stated plainly.** (1) The Madhva viddha numbers and the Pradosha window are provisional and `verified: false` until Task 13, so a fresh install names no observance day at all. (2) `sampradaya` stays `null` until Task 0 names the family's tradition. (3) The "vriddhi from a real calendar date" case is covered synthetically, not from a printed panchang, until Task 0's dates exist. (4) Sunrise-based results before 1972 are refused (`sidereal_track` starts at 1972).
- **Type consistency.** `Site(latitude, longitude, tz)`, `Element(kind, number, name, start, end)`, `DayFacts`, `Rule`, `Viddha`, `Alternate(day, reason)`, `Observance(primary, kind, alternates, tithi_start, tithi_end)`, `observances_between`, `observances_for`, `find_next`, `PanchangProfile.margin_minutes`, `ObservanceSpec.rules/verified`, `PanchangReport`, `NextObservanceReport`, `ObservanceDay(name, label, primary, kind, alternates, explanation)` are used with the same names and argument orders in every task.
