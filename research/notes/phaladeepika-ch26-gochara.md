# Phaladeepika chapter 26, transits (gochara): what was used and what was left out

**Source:** Mantreswara's *Phala Deepika*, English translation by Dr. G. S. Kapoor (in copyright), openly available at
http://www.panchanga.lv/wp-content/uploads/2020/06/Phaladipika_Shri-Mantreswara.pdf (copy in `research/sources/`,
git-ignored). Chapter 26 is on printed pages 246-256 (PDF pages 245-255). The text file `phaladeepika.txt` loses lines
at page breaks; the PDF pages were read directly for every row.

**File:** `data/rules/phaladeepika-ch26-gochara.yaml`, **unchecked**. Every result is paraphrased (the translation is
in copyright and the repository is public).

## Used

| Verses | What | In the file |
|---|---|---|
| 1 | Transits are counted from the natal Moon sign | how houses are counted |
| 2 | The good houses for each planet | `favourable` |
| 3-7 | Vedha: the house that obstructs each good house, and the exceptions (Saturn for the Sun, Mercury for the Moon, the Sun for Saturn, the Moon for Mercury) | `vedha` |
| 9-24 | The result of each planet in each of the twelve houses: Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu | `effects` |

## Left out, and why

- **Ketu:** the author gives no results; the translator only guesses they are Rahu's. Ketu's position is shown, with
  no result.
- **Venus's vedha (verse 8) and Mercury's vedha for the 8th (verse 6)** were first left out because the translation's lists did not
  line up. Cross-checked on 2026-11-12 against astroveda.wikidot.com's Rasi Gochara Vedha table: Venus 1->8, 2->7, 3->1, 4->10, 5->9,
  8->5, 9->11, 11->6, 12->3, Mercury 8->1. They fit the translation's own lists in order and are now used (see `cross-verification.md`).
- **Which planets can obstruct:** "any of the planets"; we take the seven planets, Sun to Saturn, not Rahu and Ketu.
  The checker may change this.
- **Verse 30 (the part of a sign where each planet acts), verses 31-32 (strength, aspects), verse 41 (ashtakavarga
  points override the house):** refinements the bot does not compute yet. The full view says so.
- **Verses 26-29, 33-40, 42-46 (nakshatra transits, danger-to-life combinations, the limbs tables, lattas):** not
  used. Several predict death; they need a decision before any of them is shown to the family.

## Severe rows: owner's decision, 2026-11-12: show everything, hide nothing

The owner wants the bot as transparent as possible, with no filters: every row the text gives is shown, including the
severe ones. The checker only confirms each row matches the text; nothing is hidden for being unpleasant. The rows
below are shown to everyone whose Moon sign puts the planet there, children included (the under-18 note stays: it
says the texts describe adult life, which is disclosure, not a filter):
- Rahu 1st: "illness or death"; Rahu 8th: "danger to life"
- Saturn 1st: "illness, and performing funeral rites"; Saturn 9th: "... the death of an elder like a father ..."
- Saturn 2nd and 5th, Mars 5th, Mercury 5th: loss of or trouble with children

To hide a row, write it as `N: {text: "...", hidden: true}`.

## How to check

Compare each row of `effects`, `favourable` and `vedha` with the PDF pages above. Then reply **"transits checked"**
(and name any rows to hide or reword); the file gets `level: translation-checked`, `checked_by`, `checked_on`.
