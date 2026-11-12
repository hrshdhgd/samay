# Phaladeepika chapter 21, antardasha results: what was used and what was left out

**Source:** Mantreswara's *Phala Deepika*, tr. Dr. G. S. Kapoor (in copyright), http://www.panchanga.lv/wp-content/uploads/2020/06/Phaladipika_Shri-Mantreswara.pdf,
printed pages 197-207 (PDF pages 196-206), verses 3-83. Read from the PDF pages directly. **File:**
`data/rules/phaladeepika-ch21-antardasha.yaml`, **unchecked**. Every result is paraphrased.

**Used:** the result of each antardasha (sub-chapter) inside each mahadasha: all 81 pairs. The bot shows the
running pair and any pair that begins in the period (week to five years), and adds the running pair to the
"current period of life" answer. Verse 1's order of sub-chapters (the lord's own first, then in dasha order) is what
the engine already does (`vedic.antardashas`).

## Resolved by the cross-check (2026-11-12)

- **Ketu dasa, Venus and Mercury sub-chapters (verses 67 and 74)** are now used. Kapoor's translation cuts off verse 67's heading and
  labels verse 74 "Venus"; a second edition (wisdomlib.org, *Phaladeepika*, Sanskrit with translation, Adh. XXI) names 67 as the
  Venus bhukti and 74 as the Mercury bhukti in Ketu's dasa, and the contents agree. All 81 pairs are present.
- **Verse 50** (Ketu in Saturn's dasa) fits the standard order of sub-chapters.
- **Pratyantar (sub-sub) dasas:** the text applies the same results to them; the engine does not compute them yet.
- **The translator's notes** (Kapoor's, not Mantreswara's): good results come when the planet is well placed and bad ones when it is
  badly placed; Mars is "yogakarka" for Cancer and Leo lagnas. Not applied. Verse 84 says to also weigh the person's status, work
  and appearance.

## For the checker

Compare each row with the pages above. Three to confirm:
- **Verse 50** is headed "Ketu in the dasa of Jupiter" but sits in Saturn's block; used as Ketu in Saturn's dasha, which the
  verse order requires.
- **Verse 33** ends in a garbled phrase ("skilful Mercury"); **verse 52** ends "loss of wealth and rains". Both are
  paraphrased only as far as clear.
- **Verse 41** gives two views (Jupiter dasa, Mercury sub-chapter); both are kept.

Owner's decision 2026-11-12: show everything, hide nothing; the severe rows (death of the native, loss of wife or
children, diseases) stay. Reply **"antardasha checked"** with any changes, and the file gets `level: translation-checked`.
