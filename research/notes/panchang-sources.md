# Panchang observances: source survey (2026-11-21)

Status: **locations only. Nothing here is verified.** Found by web search; verse numbers come from
devotional compilations and must be checked against a text before any entry is written.

## Copyright picture
- Public domain: Kern's *Brihat Samhita* translation (1865-75), https://archive.org/details/wg1077. Not yet checked
  for the ugra/krura nakshatra passage. (The Subrahmanya Sastri translation is CC BY-NC-ND; not used.)
- In copyright (locate and paraphrase only, no verbatim quotes): G. V. Tagare's Skanda and Narada Purana
  translations (Motilal Banarsidass; shown on wisdomlib with no licence stated).
- Sanskrit only: Muhurta Chintamani scans (archive.org), Nirnaya Sindhu
  (https://archive.org/details/in.ernet.dli.2015.326603), Hemadri's Vratakhanda
  (https://archive.org/details/in.ernet.dli.2015.487034; Roman e-texts at sites.utexas.edu/sanskrit/resources/dharmasastra/caturvargacintamani/).

## Per observance
| Observance | Candidate locus | Note |
|---|---|---|
| Ekadashi | Hari Bhakti Vilasa 12.4, 12.21 (quoting Skanda Purana); Padma Purana 7.22.27 | via https://veda.harekrsna.cz/encyclopedia/ekadasi.htm; no public-domain English |
| Pradosha | Skanda Purana, Brahma Khanda, vv. 5-14, 74-78 | wisdomlib ch. 6 (Tagare) |
| Purnima, Amavasya | Kane, *History of Dharmasastra* vol. V | no primary passage found |
| Sankashti | Narada Purana pt. 1 ch. 68 v. 78 (Angaraka caturthi); Ganesha Purana, Upasana Khanda ch. 7 (blog claim) | attribution inconsistent across sites |
| Bharani | Muhurta Chintamani; Brihat Samhita | ugra/krura class; modern sites only so far |
| Krittika | same classification puts it in the mixed (mishra) group | "avoid both" rests on modern pages and a southern saying; no primary basis found |

## Cross-reference pass (2026-11-21, public-domain route)
- archive.org `wg1077` (Kern, 1865) is the **Sanskrit edition** with an English introduction, not a
  translation; chapters are garbled Devanagari OCR. Not usable as a translation. (Kern's translation ran in
  JRAS 1870-75; not yet located.)
- Located in the Subrahmanya Sastri translation (Bangalore, 1946-47; CC BY-NC-ND, so locate and paraphrase
  only), **Brihat Samhita ch. 98, "On the Functions and Properties of the Asterisms", slokas 6-11**:
  - Bharani is one of five *Ugra* ("dreadful") asterisms (with the three Purvas and Magha), said to suit
    ruining enemies, destruction, deceit, imprisonment, poisoning, setting fire, striking with weapons.
  - Krittika, with Visakha, is "tender-sharp" (mixed results).
  - **The passage does not say to avoid either day for auspicious work.** It classes them by what they
    suit. The "avoid Bharani and Krittika" guidance is a later muhurta-tradition inference (Yama/Agni
    deities, verse 4-5 lists Yama for Bharani, Agni for Krittika) and is not in this chapter.
- Still unverified at `translation-checked` (no public-domain translation in hand), so nothing ships.
  A second independent text (Muhurta Chintamani, Sanskrit) would still need a Sanskrit reader.

## Day-selection rule
Sunrise tithi governs the day (Dharmasindhu, Nirnaya Sindhu; English summary at
https://www.kamakoti.org/kamakoti/dharmasindhu/bookview.php?chapnum=3). Smarta/Vaishnava difference noted.

## Decision (owner, 2026-11-21)
No Sanskrit reader available. v1 ships computed facts only; no "why" is shown until verified.

## Convention check against the Tulu Panchanga app (2026-11-22)
Engine (provisional Smarta rules, Mangaluru, margin 6 min) vs the app's published Ekadashi, Pradosha, Purnima and Amavasya
for 2026 and 2027: 96 of 97 dates agree (tests/test_panchang_convention.py, fixture tests/fixtures/tulu_app_observances.yaml).
The one difference, Pradosha 3 vs 4 May 2027, is the window: the app uses sunset + 1/5 of the night (137 min that day),
the engine's placeholder is 72 min. The app's other definitions match ours: arunodaya = two night-muhurtas (96 min)
before sunrise; Ekadashi Smarta at sunrise, Madhwa variant when Dashami touches arunodaya. Caveat: the app is a
computation, not a printed almanac. Open: the Pradosha window should be a fraction of the night, not fixed minutes.

## Sunrise definition follows the family calendar (2026-11-22)
Family Bunts calendar (owner): Ekadashi 20 Nov 2026. At Mangaluru the Ekadashi tithi ends 06:32:01 on 21 Nov; sunrise that
day is 06:31:42 at the Sun's upper limb and 06:32:52 at its centre. Upper-limb sunrise (the Tulu Panchanga app's choice) gives
21 Nov; disc-centre gives 20 Nov, matching the family. Profile switched to disc_centre. Everything else the family gave
(Bharani 23 Nov, Krittika 24 Nov, Sankashti 27 Nov) matches either way. One date decides this; revisit when the rest of the
year's Ekadashi dates arrive. Known side effect: the Tulu date still uses the default upper-limb sunrise only in its
aparahna cutoff (the shipped cutoff is sunset, which does not use it).

## Family December 2026 list (owner, 2026-11-22)
"Good days": Ekadashi 4 Dec and 20 Dec, Poornima 24 Dec, Sankashti 26 Dec (Christmas 25 Dec). "Bad days": Amavasya 8 Dec,
Barani 21 Dec, Keertige 22 Dec. All nine tithi and nakshatra dates agree with the engine at Mangaluru
(tests/test_family_calendar.py). Note the family's own grouping: Amavasya, Bharani and Krittika are listed together as
"bad days". That grouping is the family's custom; the bot has no checked source for it (Brihat Samhita ch. 98 only classes
Bharani as fierce and Krittika as mixed, and says nothing about Amavasya), so it is recorded here, not shown to users.

## Traditional care notes: Amavasya, Bharani, Krittika (owner decision, 2026-11-22)
The bot tells users that Amavasya days, and days when the Moon is in Bharani or Krittika, are traditionally not chosen for
starting auspicious things (weddings, housewarming, new ventures). The owner holds this is a universally known muhurta
tradition, not a family custom. Sources found are modern muhurta guides that paraphrase Muhurta Chintamani
(Ramadayalu/Ram Daivajna): https://atmanandanatha.in/marriage-muhurtas/, https://dekhopanchang.com/en/learn/vivah-muhurta,
https://www.roopalia.com/en/vrat/what-not-to-do-on-amavasya-new-moon-day.html (which also cites Manusmriti 3.122-127 for
ancestor rites on Amavasya; secondary). No primary text or verse-level translation was read, so this is NOT verified. The
notes live in `traditional_care` in data/profiles/panchang-family.yaml (`checked: false`), not in data/entries, and are shown
on a separate line labelled "muhurta tradition; we have not checked the original text". Brihat Samhita ch. 98 (entries,
unchecked) calls only Bharani fierce and Krittika mixed and gives no avoid instruction; it is left as is.

## Rohini days (owner, 2026-11-25)
Family calendar marks 25 Nov and 23 Dec 2026 as auspicious. The Moon is in Rohini at sunrise (Mangaluru) on exactly those two
days in Nov-Dec (checked in tests/test_family_calendar.py); the next is 19 Jan 2027. Brihat Samhita ch. 98 (Sastri
translation, OCR read; sloka number unconfirmed) calls Rohini and the three Uttaras "Dhruva" (fixed): coronations, expiatory
rites, planting trees, laying town foundations, starting meritorious acts. Shown as a labelled tradition note
(panchang-family.yaml traditional_care, checked: false). The three Uttaras were added on 2026-11-25 at the owner's request (not yet seen on the family calendar).
