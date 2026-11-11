# Phaladeepika, life areas (chapters 5, 10, 12 and 16): what was used and what was left out

**Source:** Mantreswara's *Phala Deepika*, English translation, commentary and annotation by Dr. G. S. Kapoor (a modern,
in-copyright translation), openly available at http://www.panchanga.lv/wp-content/uploads/2020/06/Phaladipika_Shri-Mantreswara.pdf
(copy in `research/sources/`, git-ignored). Everything is **paraphrased**. Entries are in
`data/entries/phaladeepika-life.yaml`, **unchecked** until h2 checks them against the pages named in each citation.

**Chapters read:** 5 Source of livelihood (pp. 51-54), 10 Matters relating to the 7th house (pp. 111-114), 12 Matters
relating to the birth of children (pp. 121-124, start), 16 General effects of the twelve houses (pp. 155-157, start).
Not yet read: chapter 8 (planets in the houses), 9 (ascendants), 14 and 15 (assessment of houses), the rest of 12 and 16.

## What was used: the method, not the outcomes

Each entry says **what the text examines** for an area (which house, which lord, which significator) and, for marriage,
**which dasha it links to the event**. That is the part that lets a person's own chart be read. 11 entries:

| Entry | What it gives | Topic |
|---|---|---|
| `ph-10-13` and `ph-10-14` | When marriage is likely: the dasha of a planet in, aspecting or ruling the 7th house; a second rule using Venus, the Moon and Jupiter's transit | house:7 |
| `ph-10-1`, `ph-10-6` | What the text examines for marriage (7th house, its lord, Venus, the 5th) and what helps it | house:7 |
| `ph-5-1`, `ph-5-2` | How the 10th house and the navamsa of its lord show livelihood, planet by planet | house:10 |
| `ph-16-1` | The lagna and its lord: strength, placement, and moving vs staying in one place | house:1 |
| `ph-16-5`, `-7`, `-10` | What to examine for the 2nd (wealth, speech), 3rd (brothers) and 4th (mother, home) houses | house:2, 3, 4 |
| `ph-12-1` | What the text examines for children, and what it counts as favourable | house:5 |

## What was left out, on purpose

The same chapters are mostly **lists of outcomes, many of them severe**: the loss or death of a wife (ch. 10 verses 1-7, 15),
a crippled or unfaithful wife, widowhood, having no children or the extinction of the family (ch. 12 verses 2, 6, 7), a
mother's early death (ch. 16 verse 10), "a fool and without wealth" (ch. 16 verse 6). The translator himself disputes some
of them from his own experience (ch. 12, notes to verse 3). They are specific, rest on combinations samay does not
compute, and for family users could land as verdicts. They are not turned into entries. If you want any included, tell me
which, and they go in with the same guardrails as chapter XX (a fixed "not a forecast" line and a hide switch).

## How this changes the answers

For "what about marriage?", the answer already reads the 7th house (Brihat Jataka I.15) and what sits in it (chapter XX).
Once these entries are checked it also states how the text times marriage: in the dasha of a planet in, aspecting or
ruling the 7th. The next step, not built, is to **show which of the person's planets that is**: the 7th lord and the
planets in the 7th, and whether one of them is in the dasha now. That is computed from the chart, uses the dasha dates
samay already has, and would turn "the text says X" into "in your chart, this applies to the planets Y and Z, and your
running dasha is W". It still would not say that a marriage will happen.

## To check

Compare each entry in `phaladeepika-life.yaml` with the verse named in its citation (PDF pages given). Then reply
"life entries checked" with any changes. Verse 14 (`ph-10-14`) is the most compressed; check it most carefully.
