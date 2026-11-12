# Phaladeepika's timing rules: when a house bears fruit (16.31-35) and when marriage is likely (10.12-14)

**Source:** Mantreswara's *Phala Deepika*, tr. Dr. G. S. Kapoor (in copyright), printed pages 113-114 and 161-162 (PDF pages 112-113 and 160-161).
**File:** `data/rules/phaladeepika-timing.yaml`, **unchecked**; paraphrased. New topic family **when:<area>** (one per life area, 14): "when will
I get married", "when will I get a job". This is the answer to the question the whole timing work started from.

**What it does.** For each daily noon-UTC position over the next three years (exact ephemeris), it marks the days on which each condition holds
and merges them into windows. The bot prints the windows, how many days they cover, and a plain line when a condition holds on more than half
the days ("does not narrow anything"). **The book gives conditions, never dates**, and the answer says so first.

General (any house, from the lagna and again from the Moon sign, as verses 31 and 35 say): t1, t2, t3, t4, Jupiter (32), conjunction (35).
Marriage (house 7): m1 (10.12), m2 (10.13: dasha of the planet in, aspecting or ruling the 7th), m3 (10.14: dasha of the strongest of the
7th-lord's sign ruler, navamsa ruler, Venus and the Moon, while Jupiter is in a trikona from the 7th lord's sign or navamsa). The definitions are
spelled out in the YAML's `definition` fields.

## Judgment calls (for the checker)
- **"Trikona"** = the 1st, 5th and 9th from a sign (the book's own meaning), so the same sign counts.
- **"Sign or navamsa"** = either. Verses 31.1 and 10.14 say "or"; 16.32 says "and". One reading used for all.
- **"Strongest" (10.14):** the book gives no measure; the bot ranks by standing in the sign (exaltation, moolatrikona, own, friendly, neutral,
  inimical, depression) and keeps ties. Combustion and house position are not counted.
- **"Conjoined or aspect" (31.4):** same sign, or a full sight (Brihat Jataka II.13) either way. Rahu and Ketu are not counted as aspecting the 7th (m2).
- **"The dasha" (10.13, 10.14):** a mahadasha or an antardasha of that planet counts.
- **The conjunction rule (35)** is shown only when the house lord is in an own, moolatrikona or exaltation sign at birth; otherwise the answer says it
  does not apply and why. When the lagna lord and the house lord are the same planet (e.g. Mars for an Aries lagna and the 1st house), t4 and the
  conjunction rule are marked not applicable.
- **The lagna reference only for marriage (m1-m3).** Verses 31 and 35 add "Similar assessment from the Moon sign"; the general rules are repeated from it.

## Left out
- **Verse 31(5)**, the karaka of the house meeting the lagna lord or the Moon-sign lord in transit. The karaka table in chapter 15 verse 17 as printed is
  one place out (it gives Venus for the 6th and Saturn for the 7th, then runs one house early), so the translation seems to have dropped an item; and
  "conjoined with the lord" does not say natal or transit position. Not used.
- **Verses 33-34**: enmity or friendship when the lagna lord and a house lord meet in transit (the 6th, or a hostile pair): not built.
- **The pratyantar dasa** and the other timing doctrines (Jaimini, ashtakavarga transit refinements, Saturn and Jupiter double transit): not in these
  chapters.

## Reading the result
Because Jupiter and the Moon are involved, some rules hold for long stretches (Jupiter in a trikona is true a third of the time; the Moon changes
sign every two and a half days). The windows are what the book's conditions give; they are not a prediction, and for a person who has many
conditions overlapping at once the text itself gives no way to rank them.

Owner's decision 2026-11-12: nothing hidden. **For the checker:** compare each rule and its `definition` with the pages; reply **"timing checked"**.
