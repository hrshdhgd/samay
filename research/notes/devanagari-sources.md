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
