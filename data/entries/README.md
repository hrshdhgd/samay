# Knowledge entries

Plain-English paraphrases of classical verses, one YAML list per file. Nothing here is shown to a
user until its `verification.level` is `translation-checked` or `sanskrit-checked`.

```yaml
- id: brihat-jataka-2-1-sun        # unique
  topic: planet:sun                # what a question must be sorted into: kind:subject[:detail]
  english: "<our own words>"       # a paraphrase: translations are often still under copyright
  citation: {text: Brihat Jataka, chapter: 2, verse: 1, edition: "<edition read>"}
  verse:                           # optional; shown only if text_checked is true
    devanagari: "<verse>"
    roman: "<verse in Roman letters>"
    text_checked: false            # true only after comparing with a second copy of the text
  verification:
    level: unchecked               # unchecked | translation-checked | sanskrit-checked
    checked_by: <name>             # required once checked
    checked_on: 2026-11-09
    against: "<public-domain translation compared with>"   # required for translation-checked
```

Sources: public domain only. The English translation of the Brihat Jataka by N. Chidambaram Iyer
(1885) appears to be public domain (confirm on the Wellcome Collection or HathiTrust record when
writing each entry). Do not copy text from translations that are still in copyright.
