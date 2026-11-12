# Phaladeepika chapter 8, planets in houses: what was used and what was left out

**Source:** Mantreswara's *Phala Deepika*, tr. Dr. G. S. Kapoor (in copyright), http://www.panchanga.lv/wp-content/uploads/2020/06/Phaladipika_Shri-Mantreswara.pdf,
printed pages 92-103 (PDF pages 91-102), verses 1-33. **File:** `data/rules/phaladeepika-ch8-planets-in-houses.yaml`,
**unchecked**. Every result is paraphrased.

**Used:** all nine planets in all twelve houses from the lagna (108 results), shown beside Brihat Jataka chapter 20 as a
second voice in life-area and planet answers. It is the only source in samay for **Rahu and Ketu** in a house.
The text numbers its verses per planet (Sun 1-4, Moon 5-7, Mars 8-10, Mercury 11-13, Jupiter 14-16, Venus 17-19,
Saturn 20-24, Rahu 25-27, Ketu 28-33), so a citation is a range, e.g. "Phaladeepika 8.17–19".

**Conditions the text itself puts on a result (used):**
- Sun in the 1st: extra results for Cancer (cataract), Aries (eye disease), Leo (night blindness) and Libra (no wealth,
  loss of children) rising.
- Saturn in the 1st: king-like in Libra, Capricorn or Aquarius; sorrow and poverty in any other sign.
- Moon in the 1st: the text gives the waxing Moon's results and says a waning Moon gives the reverse. Kept as one row;
  the bot does not compute waxing or waning.

## Left out, and why

- **Verses 34-35:** a result is full when the planet is the same number of degrees into its sign as the lagna point is
  into the lagna sign, and weaker the nearer the planet is to the middle of the house. Computable; not applied yet.
  Verse 34 also says Rahu acts like Saturn and Ketu like Mars.
- **Kapoor's notes** (not Mantreswara's): the Brihat Jataka comparison on Saturn in the lagna, the Manglik dosha note for
  Mars in the 1st, 2nd, 4th, 7th, 8th and 12th, "the Sun has digbala in the 10th", the notes on aspects, and the example
  charts. Not used; the Manglik note is a modern doctrine worth its own source.
- **One garbled phrase:** Mars in the 2nd, "He will have tearing" (unreadable); left out of the row.
- **Where the two texts differ:** e.g. Sun in the 5th, Jupiter in the 3rd. Both are shown as written, with no ranking;
  where they conflict the person sees both sources.

## For the checker

Compare each of the 108 rows with the pages above (page numbers are in the file header). Owner's decision 2026-11-12: show
everything, hide nothing; rows on death, loss of a spouse or children and disease stay. Reply **"planets in houses
checked"** with any changes.
