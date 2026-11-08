"""Name folding for place search.

`fold` gives one comparable key per spelling (case, accents and punctuation removed, Devanagari
romanized). `skeleton` is a coarse phonetic key for Latin names, so "Kolapur", "Kolhapur" and
"कोल्हापूर" meet in the same bucket.
"""
from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_NON_WORD = re.compile(r"[\W_]+")
_CONSONANT_H = re.compile(r"(?<=[bcdfgjklmnpqrstvwxz])h")
_LATIN_ONLY = re.compile(r"[a-z ]+")
_EXTRA = str.maketrans({"ł": "l", "ø": "o", "đ": "d", "ı": "i", "æ": "ae", "œ": "oe"})
_SPELLING = str.maketrans({"c": "k", "q": "k", "w": "v"})


def _strip_marks(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if unicodedata.category(c) != "Mn")


def _romanize(token: str) -> str:
    """Devanagari word -> plain Latin. Drops the final inherent 'a' (नागपुर -> nagpur)."""
    iast = unicodedata.normalize("NFC", sanscript.transliterate(token, sanscript.DEVANAGARI, sanscript.IAST))
    iast = re.sub("ṃ(?=[pbm])", "m", iast).replace("ṃ", "n")  # anusvara: m before labials, else n
    if iast.endswith("a") and len(iast) > 2:  # short final a only; long ā is kept
        iast = iast[:-1]
    return _strip_marks(iast).lower()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    tokens = [_romanize(t) if _DEVANAGARI.search(t) else t for t in text.split()]
    text = _strip_marks(" ".join(tokens).casefold()).translate(_EXTRA)
    return _NON_WORD.sub(" ", text).strip()


def _collapse(word: str) -> str:
    return re.sub(r"(.)\1+", r"\1", word)


def _skeleton_word(word: str) -> str:
    word = word.replace("w", "v").replace("oo", "u").replace("ee", "i").replace("sh", "s").replace("ph", "f")
    word = _collapse(_CONSONANT_H.sub("", word).translate(_SPELLING))
    if not word:
        return ""
    head = "a" if word[0] in "aeiouy" else word[0]
    return _collapse(head + re.sub("[aeiouy]", "", word[1:]))


def skeleton(text: str) -> str:
    """Phonetic key of a Latin-script (or Devanagari) name; '' for other scripts."""
    folded = fold(text)
    if not _LATIN_ONLY.fullmatch(folded):
        return ""
    return "".join(_skeleton_word(w) for w in folded.split())
