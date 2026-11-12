# Cross-verification of the judgment calls (2026-11-12)

The owner asked that every judgment call be checked against other sources or targeted searches. These are the calls, what was
checked, and the outcome. The web results were summaries of modern pages and a 1950 Sanskrit-and-translation edition on
wisdomlib.org (OCR, unproofread), so treat them as supporting evidence, not as the last word; a person with the book still
checks every row.

| Call | Checked against | Outcome |
|---|---|---|
| Ashtakavarga: five lists where Phaladeepika's translation differs from Brihat Jataka | vedastro.org Bhinnashtakavarga guide; ZODIAQ guide; M.S. Mehta, *Ashtakvarga* (excerpts) | **Changed.** BJ and the standard tables agree in all five; tables now follow them. See `ashtakavarga.md`. Mercury from Mercury was a sixth difference nobody had flagged: the translation's "7" is "9" everywhere else. |
| Venus's vedha (Phaladeepika 26.8) was left out as unreadable | astroveda.wikidot.com Rasi Gochara Vedha; two further pages | **Filled in.** The nine pairs are 1->8, 2->7, 3->1, 4->10, 5->9, 8->5, 9->11, 11->6, 12->3, and fit the translation's own nine vedha places in order (it had lost two of the good houses from the first list). One page swaps the last two (11->3, 12->6); the other two and the translation's own order give 11->6, 12->3. |
| Mercury's vedha for the 8th (26.6) was missing | the same table | **Filled in:** 8->1; the other five already agreed. |
| Ketu dasha, Venus and Mercury sub-chapters (verses 67 and 74) left out | wisdomlib.org *Phaladeepika, Sanskrit with translation*, Adh. XXI (1950 edition) | **Filled in.** Its sloka 67 is the Venus bhukti and its sloka 74 the Mercury bhukti in Ketu's dasa; the contents match Kapoor's verses. All 81 pairs are now present. |
| Verse 50 of chapter 21 mislabelled (Ketu in Jupiter's dasa, but in the Saturn block) | the standard order of sub-chapters | Confirmed as Ketu in Saturn's dasa. |
| Chapter 20 verse 14, the "and/or" condition | wisdomlib chapter 20 | **Structure confirmed:** it lists the good conditions (retrograde, own sign, exalted, friendly sign, a house other than the 6th, 8th, 12th) and the adverse ones (enemy or debilitation sign, eclipsed, in the 6th, 8th, 12th) as separate lists. It also counts a **friend's sign as good**, which Kapoor's translation does not. Not changed in the code; for the checker. |
| Chapter 20 verse 41: kendra lord benefic -> adverse, malefic -> favourable; trikona lords favourable | a summary of Phaladeepika ch. 20; wisdomlib ch. 20; BPHS ch. 47 notes | **Supported** for the kendra and trikona rules. The wisdomlib text of verse 41 is too garbled to read; a summary reads the malefic-kendra clause the other way ("gives only evil"), so that clause stays for the checker. The "3rd, 6th, 11th lords always evil" clause is in Kapoor's translation but I could not confirm it from the second edition. |
| Chapter 20 verse 24, the troublesome dashas | wisdomlib chapter 20 | **Confirmed:** Saturn 4th, Jupiter 6th, Mars or Rahu 5th, a planet in the last degree of a sign, the lords of the 6th, 8th, 12th. |
| Natural benefic = Jupiter, Venus, Mercury, the waxing Moon | general Parashari convention (BPHS) | Standard; not searched. |
| Kemadruma cancellation | Brihat Jataka XIII.3 itself | The text reports the view (Garga and Parasara); shown, not decided. |
| Ketu has no transit results | not found | Kapoor says the author gives none and guesses Rahu's. Left as is. |

**Still open:** which Moon-from-Sun list (5 or 6) Brihat Jataka has in the printed book (the scan prints a 6 as "0" elsewhere); a
proofread Sanskrit text of Phaladeepika 20.14 and 20.41; whether Ketu's transit results equal Rahu's.
