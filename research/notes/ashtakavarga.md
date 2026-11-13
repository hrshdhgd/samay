# Ashtakavarga: sources, the cross-check, and every difference between the texts

**Sources:** Brihat Jataka chapter IX (Iyer 1885, public domain, pp. 92-95) for the tables; Phaladeepika chapter 23 verses 3-9
(the printed tables), 11 (what the number of points means) and 20 (the 28 rule), tr. G. S. Kapoor, pp. 220-231; and, from the web
cross-check on 2026-11-12, the standard modern tables in vedastro.org's "Mastering Ashtakavarga Part 2: Building Bhinnashtakavarga
Charts" (https://vedastro.org/blog/Mastering-Ashtakavarga-Part-2-Building-Bhinnashtakavarga-Charts.html), which agree with the
M.S. Mehta book and the ZODIAQ guide and follow Parasara. **File:** `data/rules/ashtakavarga.yaml`, **unchecked**. Rahu and Ketu
have none.

**What it does:** for each of the seven planets, one benefic point in a sign for every one of eight sources (the seven planets and
the lagna, at birth) that lists that sign among its benefic houses for the planet. 337 points in all.

## What the cross-check changed

My first version (earlier on 2026-11-12) used Phaladeepika's lists *as printed in the English translation*, because only those
reproduce the chapter's worked example. The web cross-check showed that choice was wrong: in the five places where the
translation prints something different, **Brihat Jataka and the standard modern tables agree with each other** and disagree with
the translation. The tables now use them.

| Planet from source | Used now (BJ and standard) | Phaladeepika as printed (kept under `variants`) |
|---|---|---|
| Moon from Jupiter | 1 4 7 8 10 11 12 | 1 2 4 7 8 10 11 |
| Mars from Jupiter | 6 10 11 12 | 6 8 11 12 (repeats Venus's list) |
| Jupiter from Jupiter | 1 2 3 4 7 8 10 11 | 1 2 4 5 6 9 10 11 (repeats Mercury's list) |
| Venus from Mars | 3 5 6 9 11 12 | 3 4 6 9 11 12 |
| Mercury from Mercury | 1 3 5 6 9 10 11 12 | 1 3 5 6 7 10 11 12 |
| Moon from Sun | 3 6 7 8 10 11 | (Brihat Jataka's scan reads 5, and prints a 6 as "0" elsewhere) |

Why Phaladeepika's printed example is no guide: the chapter's twelve sign totals come out only with its own printed lists
(a test shows this), and its other figures for the same example do not come out under either set (Saturn's row, "one point in the
5th from the Sun", "10 points in Leo"). So the example was worked with the translation's own lists and is not independent
evidence for them. Every list still adds up to the text's stated count for each planet (48, 49, 39, 54, 56, 52, 39 = 337), and
the loader refuses any that does not.

**Gaps filled:** the translation drops items in three lists (the Sun's points from Mercury, the Moon's from Mercury, Venus's from
the lagna), completed from Brihat Jataka and the standard tables; Brihat Jataka's scan is garbled for Venus from the Moon,
taken from Phaladeepika and the standard tables.

## Left out

- The Prastara ashtakavarga (the 96-square table by eighths of a sign, verses 15-19), the Sodhya Pinda reductions and multipliers
  (chapter 24), and counting a house from the karaka (verses 12-15). Not computed.
- Using the points to overrule a hard house (26.41). The points are shown; the verdict is not changed by them.

## For the checker

Compare the 56 lists in `tables` with Brihat Jataka IX and Phaladeepika 23.3-9, and the meanings with 23.11 and 23.20. Reply
**"ashtakavarga checked"**.

## Correction, 2026-11-13 (after reading chapter 24)

Above I wrote that Phaladeepika's own worked example "comes out only with its own printed lists". That rested on matching the **sorted twelve sign totals** of chapter 23's example, which is weak evidence
(many lists give the same multiset). Chapter 24 prints the **full per-planet rows** of the same example (26 33 28 24 40 36 26 25 24 29 27 19 in total, and each planet's twelve values). I tested whether either
table set reproduces those rows with the positions the text states (Sun and Venus in Scorpio, Jupiter in Virgo) and a search over the other four positions: **neither the Brihat Jataka / standard tables nor Phaladeepika's printed lists
reproduce more than 1 of the 7 rows.** So the book's example cannot arbitrate between the tables; it is not self-consistent as printed in this translation. The tables stay as the cross-check chose them (Brihat Jataka and the standard
modern tables, which agree). The example is no longer offered as support for Phaladeepika's printed lists; `test_phaladeepikas_worked_example_matches_only_its_own_printed_lists` tests only the weaker, true statement about the sign totals.

## Chapter 24 (read in full, not built)
Trikona and ekadhipatya reductions (shodhana) of each planet's table and the **sodhyapinda**, then uses: the father's, mother's and brothers' deaths and the native's own death by Saturn's or Jupiter's transit through a nakshatra
found by multiplying the sodhyapinda by points and dividing by 27; the number of brothers, maternal relatives and children as point counts; longevity in years (sodhyapinda x the 8th house's points / 27). Several are about other people's deaths and
many depend on the reductions, whose rules the translator says are disputed (Parasara's and others'). Not built; a candidate if the owner wants the reduction method.
