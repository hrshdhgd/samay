# Brihat Jataka chapter XX (planets in the houses) and its strength rules

**Source:** N. Chidambaram Iyer (tr.), *The Brihat Jataka of Varaha Mihira*, Madras 1885, public domain
(archive.org b2488442x). Chapter XX is on pp. 181-186; strength rules: I.13-14 (pp. 9-10), II.16-17
(pp. 20-21), translator's note (f) to VII.2 on Astangata (pp. 61-62).

**Data file:** `data/rules/brihat-jataka-ch20.yaml`. Effect texts are quoted, not paraphrased (the
translation is public domain), with these scan corrections:

| Scan reads | Written as | Where |
|---|---|---|
| digrace … hauds | disgrace … hands | XX.3, Sun 7th |
| bliud | blind | XX.3, Sun 8th |
| he subjugated by his enemy | be subjugated by his enemy | XX.2, Sun 6th. **Check the page:** "he subjugated" would be ungrammatical, but read it yourself |
| fiickleminded / bejealous | fickle-minded / be jealous | XX.5, Moon 8th / 7th |
| virtuons | virtuous | XX.5, Moon 10th |
| null be … indinstinct | will be … indistinct | XX.9, Saturn 1st |
| Ids rnnlc in 1 ife | his rank in life | XX.7, Jupiter 8th |
| Muon, Satm'u, Sagittari, Capricoru | Moon, Saturn, Sagittarius, Capricorn | II.15-17, XX.9 |
| **Jupiter "31" degrees** | **11** | VII note (f). **Assumed; check p. 62 before marking checked** |

**Judgements I made (part of the check):**
- Each line is labelled good, bad or mixed so that stanza 11's share rule can be applied.
  Mixed: Sun 1st with Aries lagna, Sun 2nd, Sun 6th, Venus 7th.
- A lagna-specific line *replaces* the general line for that house (the text says "but if…").
  Venus in Pisces is *added*, because it is about the sign, not the house.
- Strength order: exaltation, depression, moolatrikona, own, then friendly, neutral or inimical by
  the sign lord (II.16-17). Stanza 11 gives no share for a neutral sign, and the bot says so.
- Moolatrikona is by sign only, because the text gives no degree ranges.
- Variant readings in the translator's notes (Sun 6th, Sun 9th) are shown with the line, marked as notes.

**Not used:** stanza 10's Satyacharya rule for benefics and malefics in the 6th, 8th and 12th houses
(it modifies the effects in a way the text does not quantify).

**Guardrails in the bot:** quoted text only, with citation; the strength rule shown; a fixed line
saying this is a 6th-century text and not a forecast; any row can be set `hidden: true`.

**To check:** read pp. 181-186 against the `effects` rows; confirm the corrections above (especially
Sun 6th and Jupiter's Astangata limit); then set `verification: {level: translation-checked,
checked_by: <name>, checked_on: <date>}` at the top of the data file.
