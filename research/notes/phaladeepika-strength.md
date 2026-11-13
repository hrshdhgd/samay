# The six strengths of a planet (Phaladeepika 4.1-8) and what chapters 1-4 add

**Source:** Mantreswara's *Phala Deepika*, tr. G. S. Kapoor (in copyright), pp. 35-45 (PDF 34-44). **File:** `data/rules/phaladeepika-ch4-strength.yaml`, **unchecked**, paraphrased. Topic **chart:strength**
("which planet is strongest in my chart"): for each of the seven planets, which of the book's six strengths it has (time, motion, exaltation, direction, declination, position), with a bar, the strongest and weakest planets, and
(on More) the nodes and the definitions. It is a count of the book's yes-or-no tests, **not the full shadbala arithmetic** (the commentary's rupas and shastyamsas need the chesta-bala details the book leaves to other works).

## Judgment calls
Kala is two half-points (the hour suits the planet; the fortnight suits it). The bright half suits Mercury, Jupiter, Venus and the waxing Moon; the dark half the Sun, Mars and Saturn. "Full Moon" is within 36 degrees
of opposition. The Sun's "northern course" and the "north or south" for ayana strength use the ecliptic longitude only (latitude ignored), so the Moon and Mercury can differ slightly at the equator. Uchcha counts as held
at two thirds of full or more. Sthana is held in a good sign (exaltation, moolatrikona, own, friendly) or a kendra, and not held when debilitated or combust (4.7). Direction uses whole-sign houses.

## Left out
Chandrakriya, Chandra avastha and Chandravela (4.12-20: 60 + 12 + 36 states of the Moon from her place in the nakshatra; they are mostly for query charts), the year/month/day/hora lords' strength, yuddha bala (planetary war), the
commentary's rupa tables, and Bhava bala (strength of houses by dik and aspect). 4.9-11 (aspects; natural friendship preferred to temporary; Jupiter the most powerful, Venus half, Mercury half again) are noted, not applied.

## Cross-check, chapters 1-3
- **Planetary friendships (2.21-22):** all seven rows agree with the table the bot already uses (from Brihat Jataka), so that table is now confirmed from a second text.
- **The relationship rule (2.23):** natural plus temporary friendship (a planet in the 2nd, 3rd, 4th, 10th, 11th or 12th sign from another): adhimitra, friend, neutral, enemy, adhishatru. Used now for 7.23.
- **Benefic and malefic (2.27):** the waning Moon, Sun, Mars, Saturn, Rahu and Ketu are malefic; Mercury turns malefic when joined to malefics; the waxing Moon and an unjoined Mercury are benefic. Most of my detectors treat Mercury as always benefic (the book itself,
  at 4.1, does the same for strength). **Open:** applying the Mercury rule everywhere would change a few yogas; flagged for the checker, not changed.
- **Chapter 2** (planet significations, builds and temperaments) is added as 14 unchecked entries in `data/entries/phaladeepika-planets.yaml`; verses 15-32 (places, trades, animals, grains, gems, castes, seasons, directions) are not used.
- **Chapter 3** (the ten and sixteen divisions, a planet's age by degree, the named strengths Parijata..Airavata, decanate faces): not built; the named-strength count needs 13 vargas the book does not list.
- **Chapter 19:** its balance-of-dasha method differs from the standard (it divides by 60 ghatikas, not the nakshatra's own length); the translator prefers the longitude method, which is what the bot uses.

Owner's decision 2026-11-12: nothing hidden. **For the checker:** reply **"strength checked"** and **"planets entries checked"**.
