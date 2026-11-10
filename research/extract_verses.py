#!/usr/bin/env python3
"""Put Brihat Jataka verses (Devanagari and Roman letters) into the entries that cite them.

    uv run python research/extract_verses.py            # report only: show every verse and how well the two copies agree
    uv run python research/extract_verses.py --write    # add the verses that pass to data/entries/*.yaml

Text: the Devanagari comes from the sanskritdocuments.org file (ITRANS, keyed by Mizue Sugita 1994, proofread
by Radu Canahai), converted here. GRETIL's IAST file (the same 1994 keying) is used as a mechanical check on the
conversion and on typing slips. Neither is proofread by a Sanskrit reader, and the bot says so under every verse.

Only verses whose whole content an entry's English covers are mapped (II.1-3, I.4, I.15-16). Stanzas 4-11 of
chapter II mix several topics, including the caste lines the entries leave out, so they are not mapped.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

from indic_transliteration import sanscript
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "research" / "sources"
ENTRY_FILES = [ROOT / "data" / "entries" / "brihat-jataka-ch2.yaml", ROOT / "data" / "entries" / "brihat-jataka-ch1-houses.yaml"]
SOURCE_LABEL = "sanskritdocuments.org brihajjAtakam (typed by Mizue Sugita 1994, proofread by Radu Canahai), checked against GRETIL"
PASS_SCORE = 85  # similarity (0-100) between the two copies after removing spelling and sandhi differences

PLANETS = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
MAPPING: dict[str, list[tuple[int, int]]] = {f"bj-2-1-{p}": [(2, 1)] for p in PLANETS}
MAPPING |= {f"bj-2-2-names-{p}": [(2, 2)] for p in ("sun", "moon", "mercury", "mars", "saturn")}
MAPPING |= {f"bj-2-3-names-{p}": [(2, 3)] for p in ("jupiter", "venus", "rahu", "ketu")}
MAPPING["bj-1-4-kalapurusha"] = [(1, 4)]
MAPPING |= {f"bj-1-15-house-{n}": [(1, 15), (1, 16)] for n in range(1, 13)}

# Word stems that must appear in each verse (IAST, loosely folded), read off the verses and Iyer's English, so a
# wrong stanza number cannot slip through. They are stems because Sanskrit words change their endings.
EXPECT: dict[tuple[int, int], tuple[str, ...]] = {
    (1, 4): ("kalang", "bastir", "jangh"),
    (1, 15): ("tanu", "kutumb", "sahottha", "bandhu", "putra", "patn", "maran"),
    (1, 16): ("kalpa", "vikram", "randhra", "vyay"),
    (2, 1): ("manas", "duhkh", "madan", "sacivau"),
    (2, 2): ("heli", "bodhan", "krur", "avaney"),
    (2, 3): ("jiv", "bhrgu", "sikhi", "rahu"),
}


def fold(text: str) -> str:
    """IAST (either file) reduced to a coarse key: no marks, no punctuation, no doubled letters."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ḥ", "h").replace("ṃ", "m").replace("ṁ", "m")
    text = re.sub(r"[^a-z]", "", text)
    return re.sub(r"(.)\1+", r"\1", text)


def sd_verses() -> dict[tuple[int, int], list[str]]:
    """(chapter, verse) -> the verse's lines, as ITRANS, from the sanskritdocuments file."""
    raw = (SOURCES / "sd-brihajjatakam.itx").read_text(encoding="utf-8")
    marks = list(re.finditer(r"^\s*\S*adhyAyaH\s*$", raw, re.MULTILINE))
    out: dict[tuple[int, int], list[str]] = {}
    for chapter, mark in enumerate(marks, start=1):
        end = marks[chapter].start() if chapter < len(marks) else len(raw)
        lines: list[str] = []
        for number, line in enumerate(raw[mark.end():end].splitlines()):
            line = line.strip()
            if not line or line.startswith(("\\", "%", "#")):
                continue
            if not lines and "|" not in line and len(line) < 45:
                continue  # the chapter's title, not part of verse 1
            lines.append(line)
            m = re.search(r"\|\|\s*(\d+)\s*\|\|\s*$", line)
            if m:
                out[(chapter, int(m.group(1)))] = lines
                lines = []
    return out


def gretil_verses() -> dict[tuple[int, int], str]:
    text = (SOURCES / "gretil-brhajjataka.txt").read_text(encoding="utf-8", errors="replace")
    out: dict[tuple[int, int], list[str]] = {}
    for m in re.finditer(r"^BJ_(\d\d)\.(\d\d)([a-d]?)/(.*?)(?://|/)?(?:\(.*?\))?\s*$", text, re.MULTILINE):
        out.setdefault((int(m.group(1)), int(m.group(2))), []).append(m.group(4))
    return {k: " ".join(v) for k, v in out.items()}


def to_script(lines: list[str], target: str) -> str:
    """The verse's lines in the target script, without its closing '|| N ||' number."""
    cleaned = [re.sub(r"\s*\|\|\s*\d+\s*\|\|\s*$", " ||", line) for line in lines]
    out = sanscript.transliterate("\n".join(cleaned), sanscript.ITRANS, target)
    return out.replace("||", "॥").replace("|", "।") if target == sanscript.DEVANAGARI else out


def verse_blocks() -> tuple[dict[tuple[int, int], dict], list[str]]:
    sd, gr = sd_verses(), gretil_verses()
    result, report = {}, []
    for key in sorted({k for ks in MAPPING.values() for k in ks}):
        if key not in sd or key not in gr:
            report.append(f"{key}: MISSING (sanskritdocuments: {key in sd}, GRETIL: {key in gr})")
            continue
        deva = to_script(sd[key], sanscript.DEVANAGARI)
        iast = to_script(sd[key], sanscript.IAST)
        score = fuzz.ratio(fold(iast), fold(gr[key]))
        words = fold(iast)
        missing = [w for w in EXPECT.get(key, ()) if fold(w) not in words]
        ok = score >= PASS_SCORE and not missing
        report.append(f"{key[0]}.{key[1]:<3} agreement {score:5.1f}  {'OK  ' if ok else 'FAIL'} "
                      f"{('missing words: ' + ', '.join(missing)) if missing else ''}")
        result[key] = {"devanagari": deva, "roman": iast, "ok": ok}
    return result, report


def block_for(entry_id: str, verses: dict[tuple[int, int], dict]) -> str | None:
    keys = MAPPING[entry_id]
    if not all(k in verses and verses[k]["ok"] for k in keys):
        return None
    deva = "\n".join(verses[k]["devanagari"] for k in keys)
    roman = "\n".join(verses[k]["roman"] for k in keys)

    def literal(text: str) -> str:
        return "\n".join("      " + line for line in text.splitlines())

    return (f"  verse:\n    devanagari: |-\n{literal(deva)}\n    roman: |-\n{literal(roman)}\n"
            f"    text_checked: true\n    proofread: false\n    source: \"{SOURCE_LABEL}\"\n")


def write(verses: dict[tuple[int, int], dict]) -> int:
    added = 0
    for path in ENTRY_FILES:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        out, i = [], 0
        while i < len(lines):
            out.append(lines[i])
            m = re.match(r"- id: (\S+)\s*$", lines[i])
            if m and m.group(1) in MAPPING:
                j = i + 1
                while j < len(lines) and not lines[j].startswith("  citation:"):
                    out.append(lines[j]); j += 1
                out.append(lines[j])
                if j + 1 < len(lines) and lines[j + 1].startswith("  verse:"):  # already has one: replace it
                    k = j + 1
                    while k < len(lines) and (lines[k].startswith("    ") or lines[k].startswith("  verse:")):
                        k += 1
                    j = k - 1
                block = block_for(m.group(1), verses)
                if block:
                    out.append(block); added += 1
                i = j
            i += 1
        path.write_text("".join(out), encoding="utf-8")
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    verses, report = verse_blocks()
    print("\n".join(report))
    for key, v in verses.items():
        print(f"\n--- {key[0]}.{key[1]} {'' if v['ok'] else '(REJECTED)'} ---\n{v['devanagari']}\n{v['roman']}")
    if any("FAIL" in r or "MISSING" in r for r in report):
        print("\nSome verses did not pass; those entries get no verse.", file=sys.stderr)
    if args.write:
        print(f"\nwrote verses into {write(verses)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
