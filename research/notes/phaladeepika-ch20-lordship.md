# Phaladeepika chapter 20, the dasha through the houses its lord rules: what was used and left out

**Source:** Mantreswara's *Phala Deepika*, tr. Dr. G. S. Kapoor (in copyright), http://www.panchanga.lv/wp-content/uploads/2020/06/Phaladipika_Shri-Mantreswara.pdf,
printed pages 182-185 (PDF pages 181-184), verses 2-20 and the condition in verse 14. **File:**
`data/rules/phaladeepika-ch20-lordship.yaml`, **unchecked**. Every result is paraphrased.

**Used:** for the dasha of a planet that rules houses in the person's chart (whole-sign lordship from the lagna), the text's
result for each ruled house when the lord is strong (verses 2-13) and when it is weak (15-20). Shown in the "current period of
life" answer for the running mahadasha and antardasha lords, and in `dasha:<planet>` answers. Rahu and Ketu rule no houses here.

**Verse 14, the deciding condition.** The text gives the good results "only when the lord is auspiciously disposed (not in the
6th, 8th or 12th), in his own sign or sign of exaltation, or retrograde", and the adverse when he is in a 6th, 8th or 12th, an
inimical sign, his debilitation sign, or eclipsed by the Sun. The bot computes each condition and shows which ones the chart
meets, then: any adverse condition -> the weak reading; else any good one -> the strong reading; else (neither) -> **both
readings**, with a line saying the text does not decide. This is our reading of an "and/or" sentence; the checker may prefer
another (e.g. requiring all the good conditions).

## Left out

- **Verses 21-23, 25-39, 40, 42-48:** the effects of aspects and associations assigned to the dasha lord, vargottama, malefic
  dashas with antardashas of nakshatra-lords, mixed dasha/antardasha rules, the Mars and Venus raja yogas, the "weakest planet"
  for death (31-32), maraka planets (40), kendra/trikona yogakarakas (41-47). Not computed yet; 40 and 31-32 predict death.
- **Verse 24:** the dashas that bring trouble (Saturn if fourth in the order, Jupiter sixth, Mars and Rahu fifth, a planet in the
  last degree of a sign, the lords of the 6th, 8th and 12th). Computable from the dasha sequence; not yet.
- **Verse 41 (Parasara's view):** the nature of a dasha by kendra, trikona and dusthana lordship (a benefic's kendra dasha is
  adverse, trikona lords are favourable, the lords of the 3rd, 6th and 11th always evil, the Sun and Moon free of the 8th-house
  stigma). Computable and valuable; the next step on this chapter.
- **Verse 30:** the fraction of the result by the planet's sign (full in exaltation, 3/4 moolatrikona, 1/2 own, 1/4 friend's...):
  the bot shows the sign standing but does not scale the text.
- **Verse 43:** no planet gives the result of the house it owns "in its own antardasha". Not applied; the bot shows the lordship
  reading for the antardasha lord too.

Owner's decision 2026-11-12: show everything, hide nothing; the weak-lord rows (loss of a son, "even life may end") stay.
**For the checker:** compare each of the 24 results with the pages above, and confirm or change the verse-14 reading. Reply
**"lordship checked"**.
