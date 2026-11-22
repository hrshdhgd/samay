# Panchang core, Moon-based days and Tulu date: design (hardened)

*Sub-project 1 of 4. Date: 2026-11-21. Revised after a crucible pressure-test (5 rounds, committee verdict
"needs work" from all three reviewers; no one asked for a rethink of the core).*

## 1. Background

The family wants to know about auspicious days (Ekadashi and similar), with the reason, and about days
traditionally treated with care ("barani-keertige", read as Bharani and Krittika). The family uses the
Bunts/Tulu **solar (sauramana)** calendar, so a lunar-only answer would not match the calendar they read.
samay has no tithi, karana or nakshatra-of-the-day calculation yet; sunrise and sunset exist in
`engine/daylight.py`.

The wider request is four sub-projects, each with its own spec, plan and implementation:
1. **Panchang core, Moon-based days and Tulu date (this spec).**
2. Alerts delivery: morning brief and an evening-before heads-up.
3. Personal timing: Chandrashtama, Tara Bala (needs the natal Moon).
4. Festivals and other Sun-based days: needs lunar-month naming and regional rules.

## 2. Scope

In scope:
- Tithi, nakshatra, karana, yoga with start and end times for a place and date, using the place's **local**
  sunrise, sunset and timezone.
- Per-observance day selection for Ekadashi, Pradosha, Purnima, Amavasya, with one primary date and an
  alternate when ambiguous.
- Bharani and Krittika as computed nakshatra facts (no care-day label, see 7).
- **Tulu month and day-of-month**, with the Sun's ingress time.
- Natural-language Q&A only (no new command): "is today special?", "when is the next Ekadashi?", "what is
  Ekadashi?".

Out of scope: festivals, lunar-month names, personal timing, push alerts, Sankashti (weak sourcing, needs
moonrise), any prediction.

## 3. Decisions (all owner-confirmed)

| Decision | Choice |
|---|---|
| Day selection | **Per-observance rules stored as data**, not one global rule. Each rule names its instant or window and has explicit kshaya (no match) and vriddhi (two matches) tie-breaks. |
| Ambiguity | Every result has one **primary date**; when ambiguous, an **alternate** is attached and the reply says "show both, a local panchang may differ". |
| Rule differences | Smarta, Vaishnava or Madhva, Dashami-viddha and similar are **named alternates**. `sampradaya` has **no default**: the bot refuses to pick until it is set. |
| Margin N | Covers **calculation error only**, measured from the engine's own sensitivity (see 8). Rule differences are never absorbed by widening N. |
| Local time | All sunrise, sunset and day boundaries are the user's local ones, with the place's own timezone and historical offsets. |
| Windows | The v1 rule format has a **window primitive**: "tithi prevails during [offset from sunrise or sunset, length]". Offsets (arunodaya, Pradosha) are profile parameters. |
| Sourcing | Day-selection conventions live in profiles, cited to a published calendar that states its rules. Explanations are a separate, non-blocking track (see 7). Any openly available translation may be used to check an entry (private family use); verbatim quotes stay public-domain only. |
| Surface | Natural-language Q&A through `qa.py` into a new table-driven `panchang_qa.py`. |
| Reference app | **Tulu Panchanga** (Apache-2.0, github.com/maheshraikg/tulu-panchanga), plus the family's printed panchang, which is still to be identified. |

## 4. Engine: `samay/engine/panchang.py` (pure, imports nothing else from samay)

- Core function takes **`(date, location)`** and returns facts for that location. There is no "asker" concept
  inside the engine, so per-person and per-family alerts (sub-project 2) need no change to its output shape.
- `panchang_at(utc)`: tithi (1-30 with paksha), nakshatra and pada, karana, yoga, each with start and end.
- `tithi_prevails(window)`: the window primitive. A rule is evaluated at an instant or over a window; kshaya
  and vriddhi are resolved by the rule's tie-break and reported (never silently skipped).
- `find_next(observance, location, from_date)` uses the same rule evaluation and surfaces alternates.
- Sunrise definition (upper limb, standard refraction 34′, elevation 0) is a profile field, not code.
- Dates outside DE440s (1849-2150) get a plain "I can't compute that far" reply.

### Tulu date: `samay/engine/tulu.py`
- Month from the Sun's sidereal sign (Mesha = Paggu, Vrushabha = Besha, Mithuna = Kaarthel, Karkataka = Aati,
  Simha = Sona, Kanya = Nirnala, Thula = Bonthel, Vrushchika = Jarde, Dhanu = Perarde, Makara = Ponni,
  Kumbha = Mayi, Meena = Suggi).
- **Day 1 is not "days since ingress".** Which civil day starts a month when the ingress falls late in the day
  is a disputed setting: `sankranti_cutoff` in `data/profiles/tulu.yaml` (sunrise, sunset, midnight,
  aparahna or next-day variants, the same options the reference app exposes).
- The Tulu date and the tithi observance use the **same local-day boundary**, so one reply cannot disagree
  with itself.
- The reply states "computed by rule X" and prints the exact ingress time. Within the window where the
  cutoff rules disagree, it also shows the neighbouring day and says the month starts today or tomorrow
  depending on convention.
- The cutoff is chosen from 6-10 **anchors from the family's own calendar** (Bisu as Paggu 1, sankranti days,
  Aati start), recorded as "family calendar, N anchors". These anchors become the regression suite for
  sub-project 4.

## 5. Service: reference location

`service.py` gets a thin `family_reference` layer: one configured reference location per family that resolves
the single canonical date for the family chat. A person's own-sunrise date is an optional "at your place"
note shown only when it differs. The reference location is a **separate setting** from the saved home that
`/brief` uses. Whether alerts are per-person or per-family is decided in sub-project 2 and needs no engine
change.

## 6. Q&A routing

`qa.py` stays thin. `samay/panchang_qa.py` is **table-driven** (a new observance is a data row, not a new
parsing path) and holds keyword sorting, date parsing (today, tomorrow, weekday, explicit date) and answer
assembly. New topic keys: `panchang:day`, `panchang:next:<observance>`, `observance:<name>`. The place comes
from the family reference location, or the saved home. All user-facing wording is in `render/`; a local
model may reword but never add facts. Outcome questions ("will Ekadashi bring me luck?") still get the
existing "outside known topics" reply.

## 7. Explanations: a separate, non-blocking track

- Computed facts always ship. An explanation ships only when its entry (`data/entries/`, existing schema) is
  `translation-checked` against an openly available translation. An empty or unverified entry is a valid
  state and shows as "computed fact only". It never holds up a release.
- **Located so far:** Bharani and Krittika classification (Brihat Samhita ch. 98, slokas 6-11, Sastri
  translation) and Pradosha (Skanda Purana, Brahma Khanda, vv. 5-14, 74-78, Tagare translation).
  Ekadashi, Purnima and Amavasya passages are still unread.
- **Bharani and Krittika wording follows the text:** Bharani is *ugra* (fierce, suits harsh work), Krittika
  *mixed*. The text gives no instruction to avoid either. No care-day label ships in v1. The reply says
  plainly that "barani-keertige" is a family or local custom the bot has no source for, and states only
  the classification. If a source for the custom is found later it becomes a separately labelled entry.
- A time-boxed sourcing spike reads the Ekadashi, Pradosha, Purnima and Amavasya passages (Kamakoti
  Dharmasindhu summary plus one English translation). A rule still unreadable after the time-box ships its
  computed fact with no day-selection claim.

## 8. Verification (two layers, never mixed)

1. **Calculation.** Pin every convention in the profile (sunrise definition, ayanamsa, windows, per-observance
   tie-breaks). Verify tithi, nakshatra, karana and sunrise times against an independent computation (Swiss
   Ephemeris, or a separate Skyfield run) under the **same** conventions. Pass: all ~15 dates within 1 minute
   (several latitudes, one southern-hemisphere place, one DST boundary, and dates chosen near
   tithi-at-sunrise edges). N is set from the engine's sensitivity to ±1′ in sunrise and ayanamsa variants.
2. **Convention.** A year of Ekadashi, Pradosha, Purnima and Amavasya dates is compared with published
   sources, each **tagged with the profile it matches**: the Tulu Panchanga CSV exports for Mangaluru, and
   the family's printed panchang. The fixture deliberately includes that year's kshaya and vriddhi cases.
   Zero unexplained mismatches; every divergence is listed by cause in `known_divergences.yaml`.
   Published sources are a convention-diff report, **never used to tune N**.

Note: the reference app is itself a computation under stated conventions, not ground truth. Its own
`docs/VERIFY.md` lists what still needs a priest's confirmation. It checks calculation and the Tulu day-1
rule well; it cannot say which Ekadashi tradition the family follows.

Before committing: `uv run ruff check` and `uv run pytest -q`.

## 9. Order of work

0. **Demand and oracle gate (owner).** Identify the family's printed panchang and who decides Ekadashi
   dates; copy 10-15 real dates, including some Smarta/Madhva splits, as the first fixtures. Hand-send two
   weeks of observances computed by the engine to the family and see whether anyone replies or compares
   them with the printed copy. Build the Q&A surface only if they do; otherwise the first deliverable is a
   static table in the family's convention from the same engine.
1. Profile fields and rule format (window primitive, tie-breaks).
2. Engine, Tulu date, anchors, calculation layer of verification.
3. Convention layer of verification, `known_divergences.yaml`.
4. `panchang_qa.py` and rendering.
5. Explanation entries as sourcing allows.

## 10. Acknowledged risks

- The family's printed panchang and Ekadashi convention are still unknown. If the family is Madhva, a
  Smarta-first reading would be wrong for them; the no-default `sampradaya` field prevents silent guessing.
- Demand is unproven until gate 0 is run.
- "Verified" means "matches one openly available translation". There is no Sanskrit reader.
- The reference app is a computation, not a printed almanac.
- Many explanations will ship empty at first.
- Per-person versus per-family alerts is deferred to sub-project 2.
- Honest framing stays: traditional interpretation, not prediction, and no answer implies one.
