# Panchang core and Moon-based days: design

*Sub-project 1 of 4. Date: 2026-11-21.*

## 1. Background

Users want to know about auspicious days (Ekadashi and similar) with an explanation of why, and about
days traditionally treated with care (Bharani, Krittika). samay has no tithi, karana or
nakshatra-of-the-day calculation. Natal nakshatras exist in `engine/vedic.py`; sunrise and sunset exist in
`engine/daylight.py`.

The wider request is split into four sub-projects, each with its own spec, plan and implementation:

1. **Panchang core and Moon-based days (this spec).**
2. Alerts delivery: observance in the morning brief and an evening-before heads-up.
3. Personal timing: Chandrashtama, Tara Bala (needs the natal Moon).
4. Festivals and Sun-based days: needs lunar-month naming and a regional-rules decision.

## 2. Scope

In scope:
- Compute tithi, nakshatra, karana and yoga, with start and end times, for a place and date.
- Detect Moon-based observances: Ekadashi, Pradosha, Purnima, Amavasya, Sankashti Chaturthi, and the
  care-days Bharani and Krittika.
- Explain each observance from a cited, verified entry.
- Answer on demand through chat Q&A (no new command): "is today special?", "when is the next Ekadashi?",
  "what is Ekadashi?".

Out of scope: festivals, lunar-month names, personal timing, morning-brief push, any prediction.

## 3. Decisions made

| Decision | Choice |
|---|---|
| Ekadashi day selection | Smarta rule: the tithi prevailing at local sunrise. Stored in `data/profiles/*.yaml`. Vaishnava rules can be added later as a profile option. |
| Sourcing | Only observances whose explanation can be verified against an openly available text ship. Entries below `translation-checked` are never shown. |
| Surface | Natural-language Q&A only; routing through `qa.py`. |
| Rules storage | Explanations as `data/entries/` YAML; observance detection in the engine. Not `data/rules/` (those are chart conditions). |

## 4. Engine: `samay/engine/panchang.py`

Pure; imports nothing else from samay. Reuses the existing Moon and Sun longitudes and `daylight` sunrise.

- `panchang_at(utc) -> Panchang`: tithi (1-30 with paksha), nakshatra and pada, karana, yoga, each with its
  start and end time. Longitudes are sidereal degrees in [0, 360); times are timezone-aware UTC.
- `day_panchang(place, date) -> DayPanchang`: values prevailing at local sunrise (and sunset for Pradosha),
  plus the tithis and nakshatras that begin or end during that day.
- `observances(day) -> tuple[Observance, ...]`: matched on the computed day, not a stored table.
  - Ekadashi: tithi 11 at sunrise, either paksha.
  - Pradosha: tithi 13 prevailing at sunset.
  - Purnima: tithi 15 at sunrise. Amavasya: tithi 30 at sunrise.
  - Sankashti Chaturthi: Krishna-paksha Chaturthi, decided by moonrise (see risks).
  - Bharani, Krittika: Moon in that nakshatra at sunrise.
- `find_next(observance, place, from_date) -> date`: day-by-day forward search.
- Disputed choices (day-selection rule, sunrise definition) come from the profile, and the profile stamp
  is attached to every answer.

## 5. Entries: `data/entries/panchang-observances.yaml`

One entry per observance in the existing entry schema: topic `observance:<name>`, `system: any`, an English
paraphrase in our own words, a citation (text, chapter or verse, edition) and a `verification` block.

Two layers of output:
- **Computed facts** (tithi, nakshatra, karana, yoga, times) are always shown: they are calculation.
- **An observance flag with its "why"** is shown only when its entry is verified. An observance with no
  verified entry is not flagged at all.

Care-days (Bharani, Krittika) are framed as traditional guidance for starting new ventures, never as a
prediction. That wording lives in the entry, so the engine never invents it.

## 6. Q&A routing

`qa.py` stays thin. New module `samay/panchang_qa.py` holds keyword sorting, date parsing (today, tomorrow,
weekday names, explicit dates) and answer assembly; `qa.py` calls it.

New topic keys, following `kind:subject:detail`:
- `panchang:day`: "is today special?", "what's the tithi?", "is tomorrow auspicious?"
- `panchang:next:<observance>`: "when is the next Ekadashi?"
- `observance:<name>`: "what is Ekadashi?", "why is it auspicious?"

The place is the user's saved home (the one `/brief` uses). With no home set, the bot asks through the
existing `flow.begin_home()`. All user-facing wording lives in `render/`. The local model may reword but
never add facts. Questions about outcomes ("will Ekadashi bring me luck?") still get the existing
"outside known topics" reply.

## 7. Errors

- Dates outside the DE440s range (1849-2150): a plain "I can't compute that far" reply.
- Ambiguous or unparseable date: ask which date was meant; do not guess.
- No verified entry for an observance: no flag, facts only.

## 8. Testing and verification

1. **Astronomy:** about 15 dates (several latitudes, one southern-hemisphere place, one DST boundary)
   compared with published panchang data in a fixture like `tests/fixtures/rahu_kaala_published.yaml`, each
   figure recording its source. Target: boundaries within a few minutes.
2. **Observance rules:** one test per rule. Ekadashi dates for a full year are cross-checked against two
   independent published calendars; each disagreement is explained by a convention difference or fixed.
3. **Entries:** loading, the verified gate, and the "no verified entry, so no flag" case.
4. **Routing:** sample questions map to the right topic key; date parsing cases.
5. **Explanations:** each entry is read against an openly available text and promoted to
   `translation-checked` only when it matches.

Before committing: `uv run ruff check` and `uv run pytest -q`.

## 9. Risks

- **Sources may be thin.** Ekadashi, Purnima and Amavasya are likely well sourced. Pradosha, Sankashti and the
  Bharani and Krittika guidance are uncertain. The first plan task is a source survey; the launch set is
  whatever passes, possibly three or four observances.
- **Sankashti needs moonrise.** `daylight.py` has no Moon rise function, and the Moon can fail to rise on
  some dates. If this proves hard, Sankashti moves out of v1 and this spec is updated.
- **Regional disagreement.** Some dates differ by tradition even under the Smarta rule (a tithi split around
  sunrise). Answers state which rule produced the date via the profile stamp.
- **Framing.** Auspicious and inauspicious labels are traditional guidance. The disclaimer stays and no
  answer implies a prediction.
- **Interpretation of the request.** "Barani-keertige" is read as Bharani and Krittika nakshatra days.
