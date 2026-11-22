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
