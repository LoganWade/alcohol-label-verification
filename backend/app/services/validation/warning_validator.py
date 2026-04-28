"""Dedicated Government Warning validator.

Independent of the generic comparator because the warning has structural
rules the generic path does not enforce:

- The literal header "GOVERNMENT WARNING" must appear in all caps. Wording
  alone matching is not sufficient.
- The body wording must match the statutory text after normalization.
- If OCR confidence on the warning region is poor, the validator returns
  ``Uncertain`` with a reason rather than guessing.

Jenny Park's testimony in the assignment specifically describes title-case
warning headers as a common abuse mode, which is why this lives outside the
generic comparator.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from app.core.constants import (
    DEFAULT_GOVERNMENT_WARNING,
    FUZZY_MATCH_THRESHOLD,
    GOVERNMENT_WARNING_HEADER,
    Confidence,
    FieldStatus,
)
from app.schemas.fields import ExtractedField
from app.schemas.review import WarningValidation
from app.services.validation.normalizers import normalize_for_comparison

_LOW_CONFIDENCE = {Confidence.LOW, Confidence.UNCERTAIN}


def validate_warning(
    extracted: ExtractedField,
    expected_text: str | None = None,
) -> WarningValidation:
    """Validate the Government Warning region from a label.

    ``expected_text`` defaults to the statutory text when not supplied.
    """

    expected = expected_text if expected_text is not None else DEFAULT_GOVERNMENT_WARNING
    raw = extracted.raw_text

    # No warning text was extracted at all.
    if not raw:
        return WarningValidation(
            status=FieldStatus.MISSING,
            header_caps_ok=False,
            wording_match=False,
            raw_text=None,
            expected_text=expected,
            reason="No Government Warning text was detected on the label.",
            evidence_bbox=None,
        )

    # OCR confidence on this region is too low to make a structural claim.
    if extracted.confidence in _LOW_CONFIDENCE:
        return WarningValidation(
            status=FieldStatus.UNCERTAIN,
            header_caps_ok=False,
            wording_match=False,
            raw_text=raw,
            expected_text=expected,
            reason=(
                "OCR confidence on the warning region is low. The text may be "
                "correct but cannot be verified automatically; please confirm "
                "visually."
            ),
            evidence_bbox=extracted.evidence_bbox,
        )

    # Header check: the literal string must appear in all caps. Use the raw
    # extracted text (case-sensitive) deliberately.
    header_caps_ok = GOVERNMENT_WARNING_HEADER in raw

    # Wording check: normalize both sides for comparison. Token_set_ratio
    # tolerates whitespace and minor OCR noise without smoothing away
    # substantive wording differences.
    raw_norm = normalize_for_comparison(raw)
    expected_norm = normalize_for_comparison(expected)
    wording_score = fuzz.token_set_ratio(raw_norm, expected_norm)
    wording_match = wording_score >= FUZZY_MATCH_THRESHOLD

    if header_caps_ok and wording_match:
        return WarningValidation(
            status=FieldStatus.MATCH,
            header_caps_ok=True,
            wording_match=True,
            raw_text=raw,
            expected_text=expected,
            reason="Header is all caps and wording matches the expected text.",
            evidence_bbox=extracted.evidence_bbox,
        )

    reasons: list[str] = []
    if not header_caps_ok:
        reasons.append(
            "Header 'GOVERNMENT WARNING' is not in all caps as required."
        )
    if not wording_match:
        reasons.append(
            f"Wording differs from the expected statutory text "
            f"(similarity={wording_score})."
        )

    return WarningValidation(
        status=FieldStatus.MISMATCH,
        header_caps_ok=header_caps_ok,
        wording_match=wording_match,
        raw_text=raw,
        expected_text=expected,
        reason=" ".join(reasons),
        evidence_bbox=extracted.evidence_bbox,
    )
