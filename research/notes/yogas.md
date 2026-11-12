# Yogas: Nabhasa (Brihat Jataka XII), Phaladeepika chapter 6, and the raja yogas of Brihat Jataka XI

Shown by the new topic **chart:yogas** ("which yogas do I have", "do I have any yogas"), each of the three sources gated by its own
rules file: `data/rules/brihat-jataka-nabhasa.yaml`, `phaladeepika-ch6-yogas.yaml`, `brihat-jataka-raja-yogas.yaml` (all **unchecked**).
Brihat Jataka effects are **quoted** (public domain); Phaladeepika's are **paraphrased** (in copyright). The lunar yogas (Brihat Jataka XIII) are in
the `chart:moon` answer already; the five Mahapurusha yogas also appear in `rules/yogas.yaml`, which /chart shows without effects.

## Nabhasa yogas (Brihat Jataka XII, verses 1-19, pp. 121-134)

All 32: 3 Asraya (Rajju, Musala, Nala), 2 Dala (Srik, Sarpa), 20 Akriti, 7 Sankhya (Vallaki to Gola). Every chart has at least one.
**Definitions** are the translator's: Akriti = the seven planets occupy exactly the named houses (all of them, no others); Asraya = all
in movable/fixed/common signs; Dala = three benefics in three kendras with no malefic in any kendra, or the reverse; Sankhya = the number
of signs. **Precedence** is the text's and the commentator's: an Akriti replaces a Sankhya (v. 10) and an Asraya (v. 12); an Asraya that is
also Kedara, Sula or Yuga counts as the Asraya, Gola stays Gola; a Dala that is also Vallaki, Damini, Pasa or Kedara counts as the Dala.
**Judgment calls:** the Dala "benefic planets" are Garga's Mercury, Jupiter, Venus (and the malefics Sun, Mars, Saturn), the Moon ignored;
for Vajra/Yava the Moon counts as benefic when waxing (the text does not say). Vajra and Yava will almost never fire: Varahamihira
(v. 6) says they cannot occur because Mercury and Venus never stand a quarter-circle from the Sun; the translator says they can in the
unequal-house (bhava) chart, which we do not use. **Left out:** nothing; the Yavanas' 1800-yoga scheme in the long note.

## Phaladeepika chapter 6 (pp. 55-82): 45 yogas

Five Mahapurusha yogas (from the lagna and from the Moon, with the count), Vesi/Vasi/Ubhayachari and Kartari (Subha/Papa), Amala,
Vasumati, Kesari, Sakata, Varishtha/Sama/Adhama, Lakshmi, Gouri, Saraswati, Srikantha, Srinatha, Virinchi, the exchanges of lords (Maha,
Dainya, Kahala: all 66 pairs, 28/30/8), Raja (9th and 10th lords together), Adhi from the lagna and from the Moon, the twelve house yogas
(Ava ... Vimala), and Phaladeepika's own names for the Sankhya counts. **Judgment calls**, each recorded in the `definition` field: "own or
exaltation" includes the moolatrikona sign; "friend's sign" uses the Brihat Jataka chapter 20 friendships; "aspected" uses the full
aspects of Brihat Jataka II.13 (all 7th; Mars 4th and 8th; Jupiter 5th and 9th; Saturn 3rd and 10th); "auspicious house" (Raja) =
not the 6th, 8th or 12th; Vesi/Vasi count Mercury, Jupiter and Venus as benefic and Mars and Saturn as malefic (the Sun is the reference,
the Moon and nodes do not count); the twelve house yogas use only the first condition of verse 57 (the house's lord in the 6th, 8th
or 12th), not the second ("the house occupied or aspected by malefics"); Harsha, Sarala, Vimala follow verses 63, 65, 69 (a lord of
the 6th, 8th or 12th in the 6th, 8th, 12th house). **Adhi differs between the books:** Brihat Jataka XIII.2 (notes) counts one or
more benefics in the 6th-8th from the Moon (so `chart:moon` shows Adhi on a single benefic), Phaladeepika (the Vyasa note) needs all
three benefics within the 6th-8th; both are shown as the books say. The text adds that a yoga delivers only if the lagna or the Moon and
the yoga planets are unblemished; the bot says it does not judge that.

### Left out of chapter 6, and why
- **Mahabhagya** (verse 14): needs the person's sex, which the bot does not hold.
- **Susubha, Pushkala, Subhamala/Asubhamala** (verses 8, 19, 21): need an adhimitra table, or the order "in regular order in the 5th, 6th and 7th"
  is ambiguous in the translation.
- **Shankha** (verse 37): the lords of a kendra and a trikona together in "an auspicious house": the lagna lord is both, so it would nearly always fire.
- **Kahala/Parvata** (verse 35): the translation gives the same definition for both; left out until another edition settles it.
- **The twelve house-by-house benefic yogas** (verses 44-56: Chamara, Dhenu, Shaurya, Jaladhi, Chhattra, Astra, Kama, Astra (8th), Bhagya, Khyati,
  Parijata, Musala): house occupied or aspected by benefics, its lord unburnt in an "auspicious house" in own or exaltation sign. Needs combustion
  and aspect together; a candidate for later.
- **Verse 70** (the strong 6th/8th/12th lords with weak 1st/4th/9th/10th lords): a second Duryoga; not built.
- **Kemadruma additions** from Jataka Parijata (Kapoor's note), Saravali's Sunapha counts: not Mantreswara's.

## Raja yogas (Brihat Jataka XI, pp. 112-120): 18 configurations + verses 1 and 13

Used: verses 4a, 4b, 5 (three), 6 (two), 7 (four), 8 (two), 9, 10, 11, 14, 18 (two); verse 1 (three or more planets in exaltation:
tyrannical, good, or both, by whether they are malefic, benefic, or mixed); verse 13 (three or more strong planets in own/exaltation/moolatrikona
signs: king if of a king's family; five or more: even from a low family; fewer: only rich), counting planets in those signs without measuring "powerful".
**Left out:** verse 2 (the 16 + 16 yogas of Mars, Saturn, Sun, Jupiter in exaltation as lagna, with the Moon in Cancer: the translator's counting
note is hard to follow), verse 3 (the 22 groups of planets aspecting a vargottama lagna or Moon, 528 in all), verses 15-17 and 20 (the
planets "in the 3rd, 1st and 11th" or "the other planets in the 11th" are assigned only through the commentator's different readings), and
verse 19 (the dasha timing of a raja yoga). These are rare configurations: expect the answer to say none is present.
Verse 12: "persons born under the various yogas described above, though they may be born in low families will become kings".

Owner's decision 2026-11-12: nothing hidden. **For the checker:** reply **"nabhasa checked"**, **"chapter 6 yogas checked"**, **"raja yogas checked"** after comparing.
