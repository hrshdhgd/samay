# Every prediction method in our two texts, and what it would take to use it

Written 2026-11-12 to plan how much of the two texts samay can use. Sources: **Brihat Jataka** (BJ, Varahamihira, tr. N.
Chidambaram Iyer 1885, public domain) and **Phaladeepika** (PD, Mantreswara, tr. G. S. Kapoor, in copyright, so
paraphrase only). Both have 28 chapters. **Read** means the chapter was read for samay; **contents** means only the
table of contents and chapter openings were read, so the scope is from the contents and needs reading before building.

**What the engine computes already:** the sidereal chart (planets, lagna, whole-sign houses), navamsa, nakshatra and
pada, Vimshottari mahadasha and antardasha, strength by sign (exaltation to depression), combustion (astangata),
sunrise and sunset, 8 yogas (`rules/yogas.yaml`), and transits over any period (`engine/gochara.py`).

**Ratings.** *Value*: how often the family's kind of question needs it (see `research/what-people-ask.md`). *Effort*:
S = data plus an existing pattern; M = a new calculation; L = a new subsystem.

## Already in samay

| Method | Source | Status |
|---|---|---|
| Planet meanings, house meanings, Kalapurusha | BJ I-II | checked entries |
| A planet in a house, with the text's strength rule | BJ XX (read) | checked, shown |
| Mahadasha general results | BJ VIII (read in part) | checked entries |
| Transits from the Moon sign, with vedha | PD 26.1-24 (read) | built 2026-11-12, **awaiting check** |
| What the text examines for marriage, career, children and houses | PD 5, 10, 12, 16 (read in part) | **awaiting check** |
| Nakshatra name syllables | modern tables | built, not wired into the bot |

## Ranked: the best next steps

| # | Method | Predicts | Source | Needs | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| 1 | **Antardasha results**: each of the 81 sub-periods in each mahadasha | what a sub-chapter (about 1-3 years) brings | PD 21 (contents); BJ VIII (in part) | antardashas (have) | very high | S | The best single upgrade to "my future" and the outlooks: the year view would say what the running and next sub-chapter bring. |
| 2 | **Planets in houses, second text** | life themes per house | PD 8 (contents) | chart (have) | very high | S | A second voice next to BJ XX for every life-area answer; same shape as `brihat-jataka-ch20.yaml`. |
| 3 | **Ashtakavarga**: each planet's benefic points per sign, and the sum | how strongly a transit or house works; the text says points can override a bad house | BJ IX; PD 23-24 (contents) | chart (have) | high | M | Unlocks PD 26.41 for the transit outlooks ("Saturn in your 8th, but with 5 points") and house strength for life areas. A pure, testable calculation. |
| 4 | **Dasha by house lordship**: results of a dasha from the houses its planet rules and sits in; rising and falling dashas (arohini/avarohini) | how a chapter of life turns out for this chart | PD 20 (contents) | chart, dashas (have) | high | M | Makes the dasha reading personal rather than general. |
| 5 | **The Moon in each sign, and each nakshatra** | character and temperament | BJ XVII, XVI (contents) | Moon sign and nakshatra (have) | high | S | "What kind of person am I?" is one of the most common questions. Short, gentle texts. |
| 6 | **Lunar yogas**: Sunapha, Anapha, Durudhara, Kemadruma | wealth, fame, hardship | BJ XIII; PD 6 (contents) | chart (have) | medium-high | S | Planets in the 2nd/12th from the Moon. Kemadruma is a "poverty" yoga: decide on wording. |
| 7 | **More yogas**: Nabhasa (32 shape-yogas), raja yogas, wealth and poverty yogas, conjunctions of two planets | status, wealth, character | BJ XI-XII, XIV, XXI-XXII; PD 6-7, 18 (contents) | chart (have) | medium-high | M | Many rules, each simple; fits `rules/yogas.yaml`. Each needs its condition checked against the text as carefully as its result. |
| 8 | **Aspects on the Moon; the Moon in another planet's navamsa** | mind and temperament | BJ XIX; PD 18 (contents) | chart, navamsa (have) | medium | S | |
| 9 | **When a house's results come**: the text's rules for timing a house through its lord, dasha and transit | timing for marriage, children, career | PD 15-16 (contents); PD 10.13-14 (read) | dashas, transits (have) | high | M | Combines what is built; must stay "the text's method", not a date promise. |
| 10 | **Houses strong or weak; karakas** | which life areas are well supported | PD 15 (contents) | chart, strength (have) | medium | M | Underpins every life-area answer. |
| 11 | **Livelihood** | the kind of work | BJ X (not read); PD 5 (read, method only) | chart, navamsa (have) | medium | S | |
| 12 | **Avasthas** (a planet's ten "moods") and the Moon's kriya, avastha and vela | colour for planet readings | PD 3-4 (contents) | chart (have) | low-medium | M | |
| 13 | **Divisional charts** (hora, drekkana, dwadasamsa ...) and vargottama | detail for siblings, children, parents | PD 3; BJ I, XXI, XXVII (contents) | new calculations | low-medium | M | Mostly feeds other methods. |
| 14 | **Upagrahas** (Gulika/Mandi and others) | adverse influences | PD 25 (contents) | sunrise/sunset (have) | low | M | |
| 15 | **Ascetic yogas** | renunciation | BJ XV; PD 27 (contents) | chart (have) | low | S | |
| 16 | **Kalachakra dasha** | a second dasha system | PD 22 (contents) | new subsystem | low | L | Hard to compute and to explain; little added over Vimshottari. |
| 17 | **Nakshatra transits**: Saptashalaka, Sarvatobhadra, lattas | day-to-day fortune | PD 26.25-46 (read) | transits (have) | low | M | Much of it predicts death or danger; see below. |

## Methods to leave out of the family bot (decide before building)

| Method | Source | Why |
|---|---|---|
| Longevity, early death (balarishta), the time and manner of death | BJ VI-VII, XXV; PD 13-14, 17; PD 26.27-29, 33-34 | Predicts death, including children's. Computable, but not something to show to relatives. |
| Diseases from planets | PD 14 | Health predictions can mislead; the AI is already told not to give medical advice. |
| Women's horoscopy | BJ XXIV; PD 11 | Much of it (widowhood, chastity) is harmful to show today. A few neutral parts (husband's nature) could be considered. |
| Conception, birth circumstances, lost horoscopes, animal horoscopes | BJ III-V, XXVI | Not questions the family asks. |

## Not in these two texts

- **Compatibility matching (Ashtakoota / Guna Milan):** needs another source; the people feature now gives the second chart.
- **Muhurta (choosing a good time):** Muhurta Chintamani; no public-domain English translation found.
- **Remedies (gems, mantras):** not recommended here; PD 12-13 mention remedies for a few birth problems only.
- **Prashna (horary):** a separate tradition and texts.

## Suggested order

1-2 first (data only, same patterns as now, big gain), then 3 (ashtakavarga, which also sharpens the transits),
then 4-5, then the yogas (6-7). Every step follows `research/program.md`: read the chapter, paraphrase or quote,
leave out what is unclear, and nothing is shown until checked.
