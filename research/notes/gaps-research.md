# Research on the gaps (2026-11-10)

The gaps I listed: timing of events, matching two charts, baby-name syllables, remedies and gemstones, and auspicious
dates. For each: what the sources say, what was built, and what needs a decision. The owner's source policy applies:
anything openly available may be used for this private app; verbatim text only from public-domain works.

## 1. Baby-name syllables: closed (data and engine; not yet in the bot)

Each of the 27 nakshatras has four padas, so 108 naming syllables (the Avakahada chakra). Two independent sites were
parsed and compared pada by pada: [desiutils.in](https://desiutils.in/astrology/birth-star-calculator) (Roman and
Devanagari) and [hindumirror.com](https://hindumirror.com/nakshatra-starting-letters-for-baby-names/). **They agree on all
108.** Where traditions differ, the second site lists both readings; these are kept as `also`:
- **Shravana:** Khi Khu Khe Kho in one panchanga tradition, Ju Je Jo Gha in another (both in current use).
- **Rohini and Mrigashira:** Va/Ba and Ve/Be treated as one sound (`व` is closer to B in Bengali and Assamese).
- **Uttara Bhadrapada, 4th pada:** Yna, also written Na or Tra.
Two other sites reviewed by a search summary reported different spellings for Shravana and Uttara Ashadha; that is the
same Shravana split. A third (vedicmarga) rate-limited my download, so it was not compared.
Limits: both are modern pages citing the panchanga tradition (Swar Siddhanta tables), not a classical verse, so there is
no citation to a verse. Built: `data/nakshatra_syllables.yaml` and `samay/engine/syllables.py` with tests.
**Not built:** showing it in the bot. A name is chosen for a baby, so it needs the baby's birth time and place: see the
decision under "What needs a decision".

## 2. Matching two charts (Guna Milan, Ashtakoota): researched, not built

The system scores eight factors out of 36: Varna 1, Vashya 2, Tara 3, Yoni 4, Graha Maitri 5, Gana 6, Bhakoot 7, Nadi 8.
Modern guides give 18 of 36 as the usual minimum, 18-24 average, 25-32 good. Sources attribute it to Brihat Parashara Hora
Shastra and to the marriage chapter of Muhurta Chintamani (Ram Daivajna, 16th c.); **none of the pages gave a verse**, so
the attribution is unverified. The scoring tables (Yoni animals, Tara counts, Bhakoot distances, Nadi types) were not in the
search results. Muhurta Chintamani is on archive.org only as Sanskrit or Hindi scans; English translations are in copyright.
It also needs a **second person's chart**, which the bot does not hold. Status: scoring rules need a source; the second-chart
question needs a decision.

## 3. Timing of events: partly closed

- **Phaladeepika ch. 10 v. 13-14** (drafted, awaiting check): marriage in the dasha of a planet in, aspecting or ruling the
  7th, with a second rule using Venus, the Moon and Jupiter's transit.
- **Brihat Jataka** has no "when will I marry" section. Its marriage material is in the **Brihat Samhita ch. 103** (vivaha-patala),
  which Iyer also translated (1884, public domain): it reads planets in the *wedding-time* chart, not timing from the birth
  chart, so it does not answer "when".
- Job, children and other events: the tradition times them the same way, through the running dasha and transits; no source
  held states a rule per event beyond the marriage one. samay already gives the running dasha and its listed effects.

## 4. Remedies and gemstones: researched, **not recommended for the bot**

A search found that **BPHS does not map gemstones to planets**; the gem-to-planet tables come from later and vendor sources.
What BPHS does prescribe for a troublesome planet are acts: mantra recitation, worship, fire offerings, charity and
feeding, and shanti rites. Chapter numbers were not confirmed (the Santhanam translation on archive.org would settle that).
Reasons not to build it as an answer: it is advice with a cost (gemstones are expensive), the app's guardrails tell the AI
not to advise, and no source held lists remedies. If wanted, the safe version is descriptive only: "the text prescribes
mantra and charity for this planet", with the citation, and no recommendation.

## 5. Auspicious dates and times (muhurta): researched, not built

Muhurta Chintamani is the standard text; archive.org has several Sanskrit and Hindi scans (Nirnaya Sagar edition, Govind
Jyoti; a Hindi commentary of 1933) and no public-domain English translation. I could not confirm which chapter holds Rahu
Kaala; **the Rahu Kaala rule in the bot rests on calculators and one published figure, not on a text.** Reading the Sanskrit
needs a Sanskrit reader.

## What needs a decision

**Second-person lookups in the bot.** Baby names and matching both need the birth details of someone who is not the user.
Options: **(a)** a one-off flow ("for someone else") that asks the same questions, answers, and **stores nothing** (the
conversation memory already stays in RAM and expires), or **(b)** saved named profiles (encrypted like the rest, but more
personal data, including a baby's). I would build (a) first.
