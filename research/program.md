# program.md: growing the sourced knowledge entries

Written the way the autoresearch principle asks: one goal, files that are fair game, a loop, a log.

## Goal
Grow the set of **checked** entries in `data/entries/`, so the bot can answer meaning questions
with a citation. Nothing is shown to a user until an entry is checked.

**Metric:** the number of `translation-checked` (and, later, `sanskrit-checked`) entries whose
topics appear in `samay research-queue`, highest-demand topics first. An entry that fails
review does not count.

## Fair game
- `data/entries/*.yaml` (new entries, corrections)
- `research/results.tsv` (the log)
- `research/notes/` (working notes: which translation, which page)

## Fixed (read-only)
- `samay/engine/entries.py` (the rules for what may be shown). Change it only deliberately, with a spec change.
- Every `verification` block: only a person who did the check may set `checked_by`.

## Loop (one entry)
1. Pick the top topic from `uv run samay research-queue` that has no checked entry.
2. Find the verse in a **public-domain** source; record the edition and page in `research/notes/`.
3. Paraphrase it in our own words. Do not copy a translation that is still in copyright.
4. Compare the paraphrase with the public-domain English translation. Set `translation-checked`
   only if they agree, recording who checked, when, and against what.
5. Add the Devanagari verse only if its text is compared with a second copy; set `text_checked`.
6. `uv run pytest -q` (the loader rejects malformed or under-verified entries), commit.
7. Log one line in `research/results.tsv`: `commit  topic  level  status  description`.
   status is `keep`, `discard` or `crash`; discarded attempts stay in the log, honestly described.

## Constraints
- No machine translation as a check. Tools may help a reviewer read a verse; a person decides.
- No unchecked entry is ever served. No entry cites a text it was not written from.
- Simpler wins: a short faithful paraphrase beats an elaborate one.
