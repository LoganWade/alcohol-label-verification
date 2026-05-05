"""Generic field comparator.

Implements the tiered match algorithm specified in docs/architecture.md:

1. Normalize both sides for comparison.
2. If equal post-normalization -> Match (note when raw values differed).
3. If the *word sets* (lowercased alphanumeric tokens) are equal, the only
   differences are formatting noise (punctuation, whitespace, casing not
   captured by Tier 1) -> Match.
4. Otherwise compute rapidfuzz `fuzz.ratio` (Levenshtein-based, character
   level) over the normalized strings:
     >= FUZZY_MATCH_THRESHOLD         -> Match (fuzzy)
     >= FUZZY_NEEDS_REVIEW_THRESHOLD  -> Needs Review
     <  FUZZY_NEEDS_REVIEW_THRESHOLD  -> Mismatch
5. If OCR confidence on the underlying token is "low" or "uncertain",
   downgrade Match -> Needs Review (uncertainty propagates).
6. If no candidate exists for a required field -> Missing.

Why `fuzz.ratio` and not `token_set_ratio`:
  `token_set_ratio` deduplicates tokens and compares set intersections,
  which made it blind to two failure modes we care about:
  * intra-token typos (`WINERY` vs `WINEERY` scored 97.6, above the Match
    threshold) -- the typo is in only one of four tokens, so the set
    intersection still covers most of the string
  * extra/missing words (`Cabernet Sauvignon` vs `Cabernet Sauvignon
    Reserve` scored 100) -- token_set_ratio compares only the
    intersection's similarity, so adding a word at the end is free
  `fuzz.ratio` is character-level and penalizes both cases proportionally,
  while the new Tier 2 word-set short-circuit preserves "formatting only"
  matches like `STONE'S THROW WINERY` vs `STONES THROW WINERY`.

Per AGENTS.md, the raw extracted text is preserved verbatim in the response;
normalization is applied to copies only.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.core.constants import (
    FUZZY_MATCH_THRESHOLD,
    FUZZY_NEEDS_REVIEW_THRESHOLD,
    Confidence,
    FieldStatus,
)
from app.schemas.fields import ExtractedField, FieldName
from app.schemas.review import FieldComparison
from app.services.validation.normalizers import normalize_for_comparison

_LOW_CONFIDENCE = {Confidence.LOW, Confidence.UNCERTAIN}

# Lowercase alphanumeric tokens. Used for the Tier 2 word-set check.
# We strip apostrophes (straight and curly) before tokenizing so that
# possessives like `STONE'S` collapse to `stones` and match their
# apostrophe-less twin; otherwise apostrophe drops would tokenize as
# `{stone, s}` vs `{stones}` and look like a real word difference.
_WORD_TOKEN_RE = re.compile(r"[a-z0-9]+")
_APOSTROPHES = ("'", "\u2019")


def _word_set(value: str) -> frozenset[str]:
    """Return the set of lowercase alphanumeric word tokens in ``value``."""
    lowered = value.lower()
    for apostrophe in _APOSTROPHES:
        lowered = lowered.replace(apostrophe, "")
    return frozenset(_WORD_TOKEN_RE.findall(lowered))


def compare_field(
    field: FieldName,
    expected: str | None,
    extracted: ExtractedField,
) -> FieldComparison:
    """Compare a single field's expected vs extracted value."""

    raw = extracted.raw_text

    # Treat whitespace-only or empty expected values as "not supplied".
    # Frontend forms send "" rather than null for blank optional fields, so
    # without this normalization we'd compare against an empty string and
    # produce spurious Missing/Mismatch rows for fields the reviewer never
    # intended to check. Defense in depth: the frontend should also coerce
    # empty -> null before sending, but the backend must not rely on that.
    if expected is not None and not expected.strip():
        expected = None

    # Caller did not supply an expected value: nothing to compare against.
    if expected is None:
        return FieldComparison(
            field=field,
            expected=None,
            found_raw=raw,
            found_normalized=None,
            status=FieldStatus.NEEDS_REVIEW if raw else FieldStatus.MISSING,
            reason=(
                "No expected value supplied; reviewer should verify the "
                "extracted text on the label."
                if raw
                else "No expected value supplied and nothing extracted."
            ),
            confidence=extracted.confidence,
            evidence_bbox=extracted.evidence_bbox,
        )

    # Expected value supplied but nothing extracted from the label.
    if not raw:
        return FieldComparison(
            field=field,
            expected=expected,
            found_raw=None,
            found_normalized=None,
            status=FieldStatus.MISSING,
            reason="No matching text was found on the label for this field.",
            confidence=Confidence.UNCERTAIN,
            evidence_bbox=None,
        )

    expected_norm = normalize_for_comparison(expected)
    found_norm = normalize_for_comparison(raw)

    # Tier 1: normalized exact match.
    if expected_norm == found_norm:
        status = FieldStatus.MATCH
        reason = (
            "Exact match."
            if raw == expected
            else "Match after normalizing case, whitespace, and punctuation."
        )
        if extracted.confidence in _LOW_CONFIDENCE:
            status = FieldStatus.NEEDS_REVIEW
            reason += (
                " OCR confidence on this region is low; please confirm visually."
            )
        return FieldComparison(
            field=field,
            expected=expected,
            found_raw=raw,
            found_normalized=found_norm,
            status=status,
            reason=reason,
            confidence=extracted.confidence,
            evidence_bbox=extracted.evidence_bbox,
        )

    # Tier 2: word-set equality. Catches the case where Tier 1 normalization
    # missed a punctuation/whitespace-only difference (e.g. apostrophe drops,
    # extra spaces). Same words, formatting noise -> Match.
    if _word_set(expected_norm) == _word_set(found_norm):
        status = FieldStatus.MATCH
        reason = "Match after normalizing punctuation and whitespace."
        if extracted.confidence in _LOW_CONFIDENCE:
            status = FieldStatus.NEEDS_REVIEW
            reason += " OCR confidence is low; please confirm visually."
        return FieldComparison(
            field=field,
            expected=expected,
            found_raw=raw,
            found_normalized=found_norm,
            status=status,
            reason=reason,
            confidence=extracted.confidence,
            evidence_bbox=extracted.evidence_bbox,
        )

    # Tier 3: character-level fuzzy similarity. Word sets differ here, so any
    # high score means the two strings are nearly-identical at the character
    # level despite having different actual words -- typically a single-edit
    # OCR or human typo. fuzz.ratio penalizes intra-token edits and
    # extra/missing tokens proportionally, unlike token_set_ratio.
    score = fuzz.ratio(expected_norm, found_norm)

    if score >= FUZZY_MATCH_THRESHOLD:
        status = FieldStatus.MATCH
        reason = (
            f"High similarity match (ratio={score:.0f}). "
            "Minor formatting differences only."
        )
        if extracted.confidence in _LOW_CONFIDENCE:
            status = FieldStatus.NEEDS_REVIEW
            reason += " OCR confidence is low; please confirm visually."
    elif score >= FUZZY_NEEDS_REVIEW_THRESHOLD:
        status = FieldStatus.NEEDS_REVIEW
        reason = (
            f"Partial similarity (ratio={score:.0f}). The values are "
            "close but not identical; reviewer judgment required."
        )
    else:
        status = FieldStatus.MISMATCH
        reason = (
            f"Low similarity (ratio={score:.0f}). The extracted value "
            "does not appear to match the expected value."
        )

    return FieldComparison(
        field=field,
        expected=expected,
        found_raw=raw,
        found_normalized=found_norm,
        status=status,
        reason=reason,
        confidence=extracted.confidence,
        evidence_bbox=extracted.evidence_bbox,
    )
