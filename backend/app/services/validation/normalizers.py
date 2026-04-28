"""Pure normalization helpers used by the comparator and warning validator.

These helpers operate on **copies** of strings; the original raw OCR text is
preserved upstream as evidence (AGENTS.md: never mutate raw OCR before
comparison).

Each helper is small, independently testable, and free of side effects.
"""

from __future__ import annotations

import re
import unicodedata

_QUOTES = str.maketrans({
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201C": '"',  # left double quote
    "\u201D": '"',  # right double quote
    "\u2032": "'",  # prime
})

_DASHES = str.maketrans({
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign
})

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_punctuation(value: str) -> str:
    """Standardize curly quotes and unicode dashes to their ASCII equivalents."""
    return value.translate(_QUOTES).translate(_DASHES)


def collapse_whitespace(value: str) -> str:
    """Trim and collapse internal whitespace runs to single spaces."""
    return _WHITESPACE_RUN.sub(" ", value).strip()


def normalize_for_comparison(value: str) -> str:
    """Full normalization used by the comparator.

    Order matters:
    1. Unicode NFKC (compatibility composition) folds visually identical
       variants into a canonical form.
    2. Punctuation translation handles smart quotes and unicode dashes.
    3. Casefold is more aggressive than ``lower()`` for cross-locale
       comparison and is the right tool for case-insensitive matching.
    4. Whitespace collapse normalizes any remaining gaps.
    """
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = normalize_punctuation(value)
    value = value.casefold()
    value = collapse_whitespace(value)
    return value
