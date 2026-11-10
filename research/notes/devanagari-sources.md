# Devanagari verse text: why no verse is shipped

**Question:** can the bot show the Sanskrit verse (Show Sanskrit button) from a checked, usable text?

**Candidates found (2026-11-10), read from the raw files:**
- GRETIL, Varahamihira: Brhajjataka (IAST, UTF-8). Header: "Input by Mizue Sugita, December 12, 1994 ...
  THIS GRETIL TEXT FILE IS FOR REFERENCE PURPOSES ONLY! COPYRIGHT AND TERMS OF USAGE AS FOR SOURCE
  FILE." The source file's terms are not stated.
- sanskritdocuments.org brihajjAtakam.itx (ITRANS/Devanagari). Header: "Transliterated by: Mizue
  Sugita December 12, 1994; Radu Canahai ... Proofread by: Radu Canahai ... This text is prepared by
  volunteers and is to be used for personal study and research. The file is not to be copied or
  reposted for promotion of any website or individuals or for commercial purpose without permission."

**Findings**
1. The two files are **the same 1994 keying** (Sugita), the second with a later proofread. A match
   between them is therefore not an independent second-copy check.
2. Neither grants a licence to copy verses into a public repository, and the repository is public.
3. The verse itself (6th century) is public domain, but these digital copies are volunteers' work
   with stated conditions.

**Decision:** no verse text is committed or shown. The Sanskrit toggle stays built and tested but
dormant: it appears only for an entry whose verse has `text_checked: true`, and none do.

**Ways forward (need a person)**
- Ask the maintainers for permission to quote single verses with attribution (draft below), or
- have a Sanskrit reader key the verses from the printed edition (archive.org `brihatjataka00varaiala`).

Draft permission request: "We run a small, private, non-commercial family app that quotes classical
verses with citations. May we quote individual verses of Varahamihira's Brhajjataka from your text
(input by Mizue Sugita, 1994) in the app, with attribution to GRETIL / sanskritdocuments.org?"


---

## Update 2026-11-10: verses are now shown, labelled as unproofread

**Decision (owner):** include the verses. This is a private family app, so the sanskritdocuments.org text is
usable; every verse is shown with a line saying it is a typed copy that no Sanskrit reader has proofread.

**What was done** (`research/extract_verses.py`, run with `--write`)
- Devanagari and Roman letters come from the sanskritdocuments.org ITRANS file, converted with
  `indic-transliteration`. The GRETIL IAST file is a mechanical check (the same 1994 keying, so it catches
  conversion errors and slips between the two files' revisions, not errors made by the original typist).
- Agreement between the two copies after removing spelling and sandhi differences: 1.4 96.9, 1.15 94.4,
  1.16 94.2, 2.1 97.3, 2.2 94.1, 2.3 96.7 (a verse is used only at 85 or above).
- Each verse was also read against Iyer's English by the stems of the words in it (body parts in 1.4; the houses
  in 1.15 and 1.16; the planets and their names in 2.1 to 2.3). They match.
- 29 entries carry a verse: the seven planet entries (II.1), the nine names entries (II.2, II.3), the Kalapurusha
  entry (I.4), and the twelve house entries (I.15 and I.16, both stanzas, since each lists all twelve houses).
- **Not mapped:** II.4 to II.11. Those stanzas mix several topics (and include the caste lines the entries leave
  out), so showing them under an entry whose English covers only part would mislead.

**Where the Sanskrit and Iyer's English differ (check these)**
1. **II.1, Jupiter:** the verse says *jñāna-sukhe*, "knowledge and happiness (or comfort)". Iyer renders it
   "knowledge and health", and the Jupiter entry follows Iyer. Another reading, "knowledge and well-being",
   would sit between the two.
2. **I.16, the 7th house:** the verse names it *cittottha* ("born of the mind"); Iyer gives *Manmatha* ("desire").
   Close in meaning, not the same word.
3. **I.4:** the verse speaks of *kāla-aṅgāni* ("the limbs of Time"), not the word *Kalapurusha*; Iyer's
   "Kalapurusha" is his rendering of the idea.

**Still open:** a Sanskrit reader could proofread the 29 verses; setting `proofread: true` on an entry removes the
label for it.
