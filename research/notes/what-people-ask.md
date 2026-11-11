# What people ask a horoscope reader, and what samay can answer from its sources

**Method.** A web search (2026-11-10) of astrologer-advice pages found the same categories on every site
([Sulekha](https://localservices.sulekha.com/blog_what-questions-people-commonly-ask-from-astrologers_15676),
[AskAstrologer](https://askastrologer.in/what-to-ask/), [VedicMarga](https://vedicmarga.com/questions-to-ask-astrologer/),
[AstroAssured](https://astroassured.com/questions-to-ask-astrologer/) and others). Each category is matched to the
sources already in `data/`. "Deducing to life events" is done the way the texts do it: Brihat Jataka I.15 gives each
house a list of what it stands for (body, family, wealth, brothers, education, mother, home, sons, enemies, wife,
virtue, occupation, gain, loss, travel...), so a life question is read through its house, then through what sits
there in the person's chart (chapter XX), and never as a claim that an event will happen.

| Question people ask | Houses the text gives it (I.15-16 and Iyer's note) | samay status |
|---|---|---|
| Marriage, spouse, relationship problems | 7th: wife, generosity, respect | `life:marriage` |
| Career, job, business, profession | 10th: occupation, knowledge, clothes | `life:career` |
| Money, income, loans, investment | 2nd: family, wealth; 11th: gain, earnings | `life:wealth` (houses only; no advice) |
| Children, conception | 5th: sons, intelligence, previous karma | `life:children` |
| Education, studies, exams | 4th: education; 5th: intelligence | `life:education` (new) |
| Health, illness | 1st: body, limbs; 6th: enemies, kinsmen, diseases | `life:health` (houses only; no medical advice) |
| Travel, going abroad | 12th: loss, bad deeds, travels | `life:travel` (new). The text says "travels"; it does not mention settling abroad |
| Home, property, vehicles | 4th: relations, mother, cows, dwelling place, carriage, comfort | `life:home` |
| Mother | 4th | `life:mother` (new) |
| Father, teachers | 9th: deeds of virtue, father | `life:father` |
| Brothers and sisters | 3rd: brothers, bravery | `life:siblings` |
| Family, speech | 2nd | `life:family` (new) |
| Enemies, disputes, court cases | 6th: enemies | `life:enemies` (new). Describes the house only; no legal advice |
| Spirituality, merit, past karma | 5th: previous karma; 9th: deeds of virtue | `life:dharma` (new) |
| "When will...?" (marriage, job, child) | not given by the sources held | **Gap.** Timing in the tradition runs through the dasha; samay shows the running dasha and its listed effects (`future:overview`) but no source it holds dates events, and it says so |
| Compatibility of two charts (matching) | not in Brihat Jataka ch. I-XX as read | **Gap.** Needs a source on kuta/guna matching |
| Which letter should a baby's name begin with | nakshatra pada syllables | **Gap.** The nakshatra of the Moon is computed; the syllable table needs a source |
| Remedies, gemstones, mantras, doshas | not in the sources held | **Gap, and deliberately open:** no source held, and the model is told not to advise |
| Auspicious dates (muhurta), lucky numbers, colours | not in the sources held | **Gap.** Rahu Kaala is the only timing item built (from calculators) |
| Longevity, death | 8th: death, length of life | **Left out on purpose** (sensitive for the family) |

**How the answer is built for a life area:** the checked house entries (what the text says the house stands for);
from the person's chart, which sign that house is in and which planets sit there, each with chapter XX's reading
under the text's own strength rule; one line saying this cannot say whether or when anything happens; the AI's own
message follows, labelled.

**Where sources could close the gaps** (need a person to confirm availability and status): a text on marriage
matching (Ashtakuta); the nakshatra-syllable table; Phaladeepika chapters on matters of the houses and on
marriage/progeny (the PDF used for the dasha entries has them); Jataka Parijata. Phaladeepika is the most promising:
it is already downloaded in `research/sources/`, and it covers planets in each house, yogas and many life areas in
plain verses.

**Next research step:** read Phaladeepika's chapters on the houses and on specific matters (marriage, children,
livelihood, travel) and draft paraphrased entries tagged to these same life areas, for h2 to check.
