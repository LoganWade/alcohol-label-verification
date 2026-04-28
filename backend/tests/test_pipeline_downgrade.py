"""Tests for the POOR-quality confidence-downgrade ordering.

The downgrade must be applied to extracted-field confidences BEFORE
compare_field runs, otherwise a MEDIUM-confidence Match never demotes to
Needs Review via the LOW-confidence path. See pipeline.py for context.
"""

from __future__ import annotations

from app.core.constants import Confidence, FieldStatus
from app.schemas.common import BoundingBox
from app.schemas.fields import ExtractedField, ExtractedFields, FieldName
from app.services.pipeline import _apply_poor_quality_downgrade
from app.services.validation.comparison import compare_field


def _ext(text: str | None, conf: Confidence, field: FieldName) -> ExtractedField:
    return ExtractedField(
        field=field,
        raw_text=text,
        normalized_text=text,
        evidence_bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10) if text else None,
        confidence=conf,
    )


def _all(brand_conf: Confidence) -> ExtractedFields:
    """Build a complete ExtractedFields with brand_name at the given confidence."""
    return ExtractedFields(
        brand_name=_ext("Stone's Throw", brand_conf, FieldName.BRAND_NAME),
        class_type=_ext(None, Confidence.UNCERTAIN, FieldName.CLASS_TYPE),
        alcohol_content=_ext(None, Confidence.UNCERTAIN, FieldName.ALCOHOL_CONTENT),
        net_contents=_ext(None, Confidence.UNCERTAIN, FieldName.NET_CONTENTS),
        bottler=_ext(None, Confidence.UNCERTAIN, FieldName.BOTTLER),
        country_of_origin=_ext(
            None, Confidence.UNCERTAIN, FieldName.COUNTRY_OF_ORIGIN
        ),
        warning=_ext(None, Confidence.UNCERTAIN, FieldName.WARNING),
    )


class TestPoorQualityDowngradeMath:
    def test_high_drops_to_medium(self):
        before = _all(Confidence.HIGH)
        after = _apply_poor_quality_downgrade(before)
        assert after.brand_name.confidence is Confidence.MEDIUM

    def test_medium_drops_to_low(self):
        before = _all(Confidence.MEDIUM)
        after = _apply_poor_quality_downgrade(before)
        assert after.brand_name.confidence is Confidence.LOW

    def test_low_stays_low(self):
        before = _all(Confidence.LOW)
        after = _apply_poor_quality_downgrade(before)
        assert after.brand_name.confidence is Confidence.LOW

    def test_uncertain_stays_uncertain(self):
        before = _all(Confidence.UNCERTAIN)
        after = _apply_poor_quality_downgrade(before)
        assert after.brand_name.confidence is Confidence.UNCERTAIN

    def test_other_fields_also_downgraded(self):
        """Every field on the model should be downgraded, not just brand_name."""
        # Build a fields object where every field is HIGH.
        fields = ExtractedFields(
            brand_name=_ext("X", Confidence.HIGH, FieldName.BRAND_NAME),
            class_type=_ext("X", Confidence.HIGH, FieldName.CLASS_TYPE),
            alcohol_content=_ext("X", Confidence.HIGH, FieldName.ALCOHOL_CONTENT),
            net_contents=_ext("X", Confidence.HIGH, FieldName.NET_CONTENTS),
            bottler=_ext("X", Confidence.HIGH, FieldName.BOTTLER),
            country_of_origin=_ext("X", Confidence.HIGH, FieldName.COUNTRY_OF_ORIGIN),
            warning=_ext("X", Confidence.HIGH, FieldName.WARNING),
        )
        after = _apply_poor_quality_downgrade(fields)
        for name in (
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "bottler",
            "country_of_origin",
            "warning",
        ):
            assert getattr(after, name).confidence is Confidence.MEDIUM, name


class TestDowngradeAffectsComparisonStatus:
    """The reviewer-flagged ordering bug.

    With the old code (downgrade after compare_field), a MEDIUM-confidence
    Match stayed Match because compare_field never saw the downgraded value.
    With the new code (downgrade before compare_field), the same scenario
    produces Needs Review because compare_field's LOW-confidence path fires.
    """

    def test_medium_match_demotes_to_needs_review_after_downgrade(self):
        # Start with a clean MEDIUM-confidence extraction that exact-matches
        # the expected value.
        ext_before = _ext("Stone's Throw", Confidence.MEDIUM, FieldName.BRAND_NAME)
        cmp_before = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Stone's Throw",
            extracted=ext_before,
        )
        # Sanity: pre-downgrade, MEDIUM-confidence exact match should be MATCH.
        assert cmp_before.status is FieldStatus.MATCH
        assert cmp_before.confidence is Confidence.MEDIUM

        # Now simulate POOR quality: downgrade extracted, then re-compare.
        downgraded = _apply_poor_quality_downgrade(_all(Confidence.MEDIUM))
        cmp_after = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Stone's Throw",
            extracted=downgraded.brand_name,
        )
        # Post-downgrade, the comparator sees LOW confidence and demotes.
        assert cmp_after.status is FieldStatus.NEEDS_REVIEW
        assert cmp_after.confidence is Confidence.LOW
        assert "low" in cmp_after.reason.lower()
