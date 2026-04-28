"""Generic field comparator.

Implements the tiered match algorithm specified in docs/architecture.md:

1. Normalize both sides for comparison.
2. If equal post-normalization -> Match (note when raw values differed).
3. Otherwise compute rapidfuzz token_set_ratio:
     >= FUZZY_MATCH_THRESHOLD          -> Match (fuzzy)
     >= FUZZY_NEEDS_REVIEW_THRESHOLD   -> Needs Review
     <  FUZZY_NEEDS_REVIEW_THRESHOLD   -> Mismatch
4. If OCR confidence on the underlying token is "low" or "uncertain",
   downgrade Match -> Needs Review (uncertainty propagates).
5. If no candidate exists for a required field -> Missing.

Per AGENTS.md, the raw extracted text is preserved verbatim in the response;
normalization is applied to copies only.
"""

from __future__ import annotations

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


def compare_field(
    field: FieldName,
    expected: str | None,
    extracted: ExtractedField,
) -> FieldComparison:
    """Compare a single field's expected vs extracted value."""

    raw = extracted.raw_text

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

    # Tier 2: fuzzy similarity.
    score = fuzz.token_set_ratio(expected_norm, found_norm)

    if score >= FUZZY_MATCH_THRESHOLD:
        status = FieldStatus.MATCH
        reason = (
            f"High similarity match (token_set_ratio={score}). "
            "Minor formatting differences only."
        )
        if extracted.confidence in _LOW_CONFIDENCE:
            status = FieldStatus.NEEDS_REVIEW
            reason += " OCR confidence is low; please confirm visually."
    elif score >= FUZZY_NEEDS_REVIEW_THRESHOLD:
        status = FieldStatus.NEEDS_REVIEW
        reason = (
            f"Partial similarity (token_set_ratio={score}). The values are "
            "close but not identical; reviewer judgment required."
        )
    else:
        status = FieldStatus.MISMATCH
        reason = (
            f"Low similarity (token_set_ratio={score}). The extracted value "
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
