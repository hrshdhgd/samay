# Length of life, dangers at birth and the cause of death (Phaladeepika 13.6-24 and 14.12-23) — and the consent gate

**Source:** Mantreswara's *Phala Deepika*, tr. G. S. Kapoor (in copyright), pp. 130-136 and 140-143. **File:** `data/rules/phaladeepika-ch13-14-longevity.yaml`,
**unchecked**, paraphrased. Topic **chart:longevity** ("how long will I live", "when will I die"). Sensitive: one of the methods the owner chose to include.

## The consent gate (new, 2026-11-13)
- A question routed to a sensitive topic gets a **warning with two buttons** (*Show it* / *No thanks*). **Nothing is computed before the tap**
  (tested). The answer is then sent once, without the AI follow-up (the AI is never asked about these topics), with its buttons removed.
- **Sensitive:** `chart:longevity` for everyone. For a person **under 18**, also `chart:health`; the warning is stronger and names the child.
- The tap carries the person and topic in its button data, so nothing is remembered between taps and a restart loses nothing; the person's age is
  worked out again at the tap. A crafted More/Less button for a sensitive topic is ignored. Consent is asked every time.

## Used (all as the book's conditions, never dates)
13.6-7 the three classes of life and balarishta; 13.3-4 the first twelve years cannot be judged; 13.9 gandanta (the Moon or lagna within 3°20' of
a sign junction); 13.10-11 the fateful degrees of the Moon and the lagna; 13.12 five of the seven balarishta dispositions, with the book's cancellation
(benefics in a kendra or aspecting the lagna or Moon, computed and shown); 13.13 weak lagna lord or Moon-sign lord in the 6th, 8th or 12th; 13.15 the
kendra / panaphara / apoklima rule and the friendship rule; 13.16 the four stronger/weaker comparisons; 13.17; 13.21-23 the protections; 14.12-19 the
cause of death by the 8th house's planets or sign; 14.21 pain or ease at death by the 12th lord and house.

## Left out, on purpose
- **Every rule that dates or windows a death:** 13.18 (Saturn reaching the sum of four longitudes) and 13.19 (the lagna lord's transit through the 6th, 8th, 12th).
  The owner asked for the descriptive parts only and the question of windows is still open. Dasha-based death timing (14, 20.31-40) is not built either.
- **13.12(1)** (malefics in a kendra or the 8th): in the translation it fires on most charts. **13.14's pair table** (the printed table cannot be read
  unambiguously). **14.20** "the 8th lord and the 8th house a malefic": ambiguous. **14.22-23** (heaven, hell, the abode after death) and 14.24-28
  (past and future births): afterlife claims, not readings of this life.
- **Women's horoscopy** (Brihat Jataka XXIV, Phaladeepika 11) and **house strength** (Phaladeepika 15) are still to do.

## Judgment calls (for the checker)
"Weak" (13.13) = enemy or debilitation sign, or combust. "Stronger" (13.15-16) = the planet's standing in its sign (exaltation, moolatrikona, own,
friendly, neutral, inimical, depression); ties count as not stronger. Friends, neutrals and enemies come from Brihat Jataka chapter 20 and must be mutual.
"Aspect" = the full sights of Brihat Jataka II.13. "Waning Moon" = more than 180° from the Sun. The "Painless / painful" death readings take the
sign lord or a joined planet as benefic or malefic by Jupiter/Venus/Mercury vs Sun/Mars/Saturn.

Owner's decision 2026-11-12: nothing is hidden, a warning and a tap come first. **For the checker:** reply **"longevity checked"**.
