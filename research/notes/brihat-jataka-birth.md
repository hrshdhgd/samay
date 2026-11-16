# Brihat Jataka V: matters connected with birth-time (verses 1-23)

**Source:** N. Chidambaram Iyer (tr.), *Brihat Jataka*, Madras 1885, public domain, pp. 39-50, read in full. **File:** `data/rules/brihat-jataka-birth.yaml`, **unchecked** (written after "checked all" on 2026-11-13, so it still needs its own check); engine `samay/engine/birth_bj.py`; 28 coded rules.
Two topics: `chart:birth` (25 rules: father, place of birth, delivery room, lamp, midwives) and **`chart:birth_parents`** (3 rules: illegitimacy, a child deserted by its mother, and whether it dies) which is **SENSITIVE**: behind the consent gate for everyone, with `SENS_WARN_PARENTS` and a stronger one for a child.
Routing: "where/how was I born", "circumstances of my birth" -> chart:birth; "legitimate/illegitimate/deserted/abandoned" with a personal word -> chart:birth_parents.

**Judgment calls (for the checker):**
- *Sign classes (translator's note to I.17):* biped = Gemini, Libra, Virgo, first half of Sagittarius, Aquarius; aquatic = Cancer, first half of Capricorn, Pisces (centiped Scorpio, quadruped the rest). The lagna sign is classed by the lagna's own degree.
- *"Aspected by the Moon" on the lagna* = the Moon in the 7th (her only aspect); *Saturn/Mars/Sun aspecting* use the full aspects of II.13.
- *5.6 illegitimacy:* Jupiter "aspects" counts a conjunction in that sign too; the cancelling readings of Yavaneswara and Garga (the translator's notes) are all applied.
- *5.8-9 "full Moon":* the Moon between 144 and 216 degrees from the Sun (the same test as chapter 7).
- *5.19 "most powerful planet":* best standing in its sign (exaltation ... depression); ties list all. The translator's Saravali room-by-planet table and Laghu Jataka's storeys are in the file but not coded.
- *5.22 midwives:* planets strictly between the lagna and the Moon (by house); outside = 7th to 12th house (visible half) as the book's primary order; exalted or retrograde x3, own or moolatrikona x2.
- *5.17 dark spot:* the translator's Kendra reading (Yavanacharya) is not used; the 4th house only, as the text says.
- *5.18 the lamp:* the oil, wick and lamp kind are the book's imagery; the Saravali full-moon variant is not coded.

**Left out:** the lamp's direction and the entrance direction (5.18, the translator's varying readings), the cot's legs and sides (5.21 note), the body's structure and colour (5.23, same as chapter II, already built in `chart:moon` and the planet entries), the delivery-room direction of 5.20 is coded, 5.13's "mother's property" is coded.

**For the checker:** reply **"birth circumstances checked"** (covers both topics; check the three parents rules against the book most carefully).
