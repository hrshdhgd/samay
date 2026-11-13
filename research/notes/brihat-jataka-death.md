# Brihat Jataka XXV: death (verses 1-15)

**Source:** N. Chidambaram Iyer (tr.), *Brihat Jataka*, Madras 1885, public domain, pp. 207-213, read in full and checked line by line against the Sanskrit (BJ_25 in `research/sources/gretil-brhajjataka.txt`).
**File:** `data/rules/brihat-jataka-death.yaml`, **unchecked**; engine `samay/engine/death_bj.py`.

**Where it shows (MOST SENSITIVE, both behind the consent gate, stronger warning for a child):**
- Verses 1-13 (cause and manner, place, insensibility, the body) inside `chart:longevity`, after Phaladeepika 13-14.
- Verses 14-15 (the world before and after, moksha) as a new topic `chart:afterlife`, with its own warning (`SENS_WARN_AFTERLIFE`); routed only by "afterlife", "rebirth", "moksha", "salvation" or the exact phrases "past/previous/former/next/last life/birth" (so "my life next year" is not caught).

**Used:** 25.1 the planet in the 8th (fire, water, weapons, fever, unknown disease, thirst, starvation, with the translator's good/bad/indifferent work by its strength), the empty 8th aspected (humours from the translator's table, the limb from I.4), the 8th's movable/fixed/common sign;
25.2-10 as 26 coded yogas; 25.11 the 22nd drekkana when nothing above applies; 25.12 the place of death (four candidates and the most powerful, the translator's place table) and the time of insensibility; 25.13 fiery, watery, mixed and snake drekkanas; 25.14 the world before and the grade of the last life; 25.15 the next world and moksha.

**New computation:** `ephemeris.rising_sign_rest_minutes(chart)`: the minutes until the sidereal ascendant leaves its sign at the birth place (RAMC stepped and bisected; ayanamsa and obliquity held fixed). Tested against the kernel: one minute before, the sign is unchanged; one minute after, the next sign.

**Where Iyer departs from the Sanskrit and the Sanskrit is followed (marked [ ] in the file; for the checker):**
- 25.4 woman at home: Iyer "accompanied by a benefic"; Sanskrit *aśubhānvite*, joined with a **malefic**.
- 25.8 machine: Iyer "the Sun, Moon and Saturn occupy the rising sign"; Sanskrit *saurendunā*, **Saturn and the Moon**.
- 25.10 birds: Iyer "Saturn occupies the 6th"; Sanskrit *nidhane*, the **8th**.

**Judgment calls (for the checker):**
- *25.1 "unoccupied":* Iyer's reading (the Sanskrit gives the aspect rule and then the occupants). The aspecting planets are all listed with their humours, the strongest named; "powerful" is read as the best standing in its sign.
- *25.2 stones:* the Sun and Mars each in the 4th or 10th, together or apart (the dual is ambiguous); this overlaps 25.8's vehicle (Sun 10th, Mars 4th) and is shown with it. *Drowning:* Iyer's "common sign"; the Sanskrit *ubhayodaye* may mean Pisces alone (the sign rising by both head and feet, I.10).
- *25.4 prison:* two or more malefics in the 5th and 9th together, none aspected by a benefic.
- *"The 8th house contains a Sarpa/Nigala drekkana" (25.4, 25.13):* the drekkana in the 8th that corresponds to the rising one (it is the 22nd from it). Snake drekkanas from chapter XXVII's figures (Cancer 2nd, 3rd; Scorpio 1st, 2nd; Pisces 3rd), fetters Capricorn 1st. The translator's note to 25.13 lists Cancer 1st and 2nd instead of 2nd and 3rd: a third version (see the XXIII note).
- *25.5 spear (2):* all four (Sun, Mars, Saturn, waning Moon) in the 1st, 5th and 9th houses.
- *25.9 "powerful Mars":* in its own, moolatrikona or exaltation sign. *Waning:* the Moon within 180 degrees before the Sun.
- *25.11:* applies only when no cause from 25.1-10 is found (the 8th empty and unaspected, and no yoga); the movable/fixed/common place is not counted as a yoga. The "means belonging to such lord" are 25.1's (fire for the Sun...).
- *25.12 place:* "the place of the sign of a planet" is its own sign, the moolatrikona one for planets with two (the translator's note b); the Sun Leo, the Moon Cancer. *Insensibility:* the lagna's lord aspecting (full aspect, not occupying) doubles, another benefic aspecting triples, both six times (translator's note c).
- *25.13:* a drekkana's lord counted benefic (watery) for the Moon, Mercury, Jupiter and Venus; "occupied" means a planet inside that 10-degree span.
- *25.14:* the stronger of the Sun and Moon by standing; a tie shows both.
- *25.15:* Iyer's commentary reading (6th and 8th empty: the drekkana lords; or the strongest occupant of the 6th-8th); the Sanskrit names only the planet in the 7th as the alternative. Moksha by Jupiter exalted in the 6th, 8th or a kendra, or Pisces rising with Jupiter in it in a benefic's navamsa and the other six weak (inimical or depression).

**Follow-up:** Phaladeepika 14.22-28 (heaven, hell, past and future births) were left out on 2026-11-12 as "afterlife claims"; under the owner's no-filter decision they can now join `chart:afterlife` as a second source.

Owner's decision 2026-11-12: nothing hidden; warning first. **For the checker:** reply **"brihat jataka death checked"**.
