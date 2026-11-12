# Ashtakavarga: sources, the cross-check, and every difference between the two texts

**Sources:** Phaladeepika chapter 23 verses 3-9 (the tables), 11 (what the number of points means) and 20 (the 28 rule),
tr. G. S. Kapoor, printed pages 220-231 (PDF pages 219-230); and Brihat Jataka chapter IX, tr. N. Chidambaram Iyer 1885
(public domain), pages 92-95. The tables are lists of numbers (facts, not prose). **File:** `data/rules/ashtakavarga.yaml`,
**unchecked**. Rahu and Ketu have no ashtakavarga in either text.

**What it does:** for each of the seven planets, one benefic point in a sign for every one of eight sources (the seven
planets and the lagna, at birth) that lists that sign among its benefic houses for the planet. 337 points in all. Used in
two places: every planet's stay in a sign in the week-to-five-year outlooks shows the planet's own points there (and
the text's meaning of the number in the More view), and a new topic, **chart:ashtakavarga**, shows each sign's total by
house from the lagna with the text's 28 rule.

## The cross-check (why these lists)

Phaladeepika states each planet's total (48, 49, 39, 54, 56, 52, 39) and how many points each of the eight sources gives
it. The loader refuses any table that does not match, so a transcription slip cannot get in. The chapter also works one
example: the twelve sign totals `19 26 33 28 27 24 29 40 24 25 26 36` (sum 337). The Sun and Venus in Scorpio and Jupiter in
Virgo are stated; searching the other positions finds exactly one chart that gives those twelve totals under the tables in
the file (Moon Aries, Mars Leo, Mercury Sagittarius, Saturn Taurus, lagna Sagittarius), and in it the Sun's points in Taurus
and Jupiter's in Virgo are both 7, as the chapter says. That is a test (`test_the_books_worked_example_is_reproduced`).
The chapter's other figures for the example (Saturn's row, "one point in the 5th from the Sun") do **not** come out, so the
example confirms the tables only partly; the chapter's own example is not fully self-consistent either (it says Saturn has 10
points in Leo, and its table shows 7).

## Where Brihat Jataka and Phaladeepika differ (five lists; Phaladeepika's is used)

| Planet from source | Phaladeepika (used) | Brihat Jataka | Example |
|---|---|---|---|
| Moon from the Sun | 3 6 7 8 10 11 | 3 5 7 8 10 11 | cannot decide |
| Moon from Jupiter | 1 2 4 7 8 10 11 | 1 4 7 8 10 11 12 | needs Phaladeepika's |
| Mars from Jupiter | 6 8 11 12 | 6 10 11 12 | needs Phaladeepika's (it repeats Venus's list) |
| Jupiter from Jupiter | 1 2 4 5 6 9 10 11 | 1 2 3 4 7 8 10 11 | needs Phaladeepika's (it repeats Mercury's list) |
| Venus from Mars | 3 4 6 9 11 12 | 3 5 6 9 11 12 | needs Phaladeepika's |

The bot says so in the More view ("Brihat Jataka's tables differ in 5 of the 56 lists"). Whether Mantreswara or his editor
repeated a neighbouring list in two places is a question for a scholar; the choice here is only "the list that makes the
edition's own example work". Another edition or the Sanskrit could settle it.

**Gaps filled:** Phaladeepika's translation drops items in three lists (the Sun's points from Mercury, the Moon's from
Mercury, Venus's from the lagna), completed from Brihat Jataka; Brihat Jataka's scan is garbled in two (Mercury from
Mercury, Venus from the Moon), taken from Phaladeepika. All five still reproduce the example.

## Left out

- The Prastara ashtakavarga (the 96-square table by eighths of a sign, verses 15-19), the Sodhya Pinda reductions and
  multipliers (chapter 24), and the rule that a house counts from the karaka (verses 12-15). Not computed.
- Kapoor's note that 8 points is "full benefic" and 0 "adverse" (a translator's note; the text's list in verse 11 runs
  1 to 7). The text's own meaning for 0 ("loss of life") is shown.
- Using the points to overrule a hard house (26.41: a planet gets good results in a 6th, 8th or 12th house when the sign has
  many points). The points are shown; the verdict is not changed by them, and the More view says so.

## For the checker

Compare the 56 lists in `tables` with Phaladeepika 23.3-9 and Brihat Jataka IX, and the meanings with 23.11 and 23.20. Owner's
decision 2026-11-12: nothing hidden. Reply **"ashtakavarga checked"** with any changes; if you settle a disputed list
differently, change it in `tables` and the test that reproduces the example will say whether the book's numbers still work.
