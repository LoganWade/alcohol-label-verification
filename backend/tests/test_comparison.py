"""Unit tests for the generic field comparator.

These tests pin the tiered match algorithm and explicitly exercise the
"Stone's Throw vs STONE'S THROW" case Dave Morrison cited.
"""

from __future__ import annotations

from app.core.constants import Confidence, FieldStatus
from app.schemas.common import BoundingBox
from app.schemas.fields import ExtractedField, FieldName
from app.services.validation.comparison import compare_field


def _extracted(
    text: str | None,
    confidence: Confidence = Confidence.HIGH,
    field: FieldName = FieldName.BRAND_NAME,
) -> ExtractedField:
    return ExtractedField(
        field=field,
        raw_text=text,
        normalized_text=text,
        evidence_bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10) if text else None,
        confidence=confidence,
    )


class TestStoneThrowCase:
    """Dave Morrison's exact example. Must resolve to Match."""

    def test_uppercase_vs_titlecase(self):
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Stone's Throw",
            extracted=_extracted("STONE'S THROW"),
        )
        assert result.status is FieldStatus.MATCH
        assert "normaliz" in result.reason.lower()

    def test_curly_apostrophe(self):
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Stone's Throw",
            extracted=_extracted("Stone\u2019s Throw"),
        )
        assert result.status is FieldStatus.MATCH


class TestExactMatch:
    def test_identical_strings(self):
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Old Tom Distillery"),
        )
        assert result.status is FieldStatus.MATCH
        assert result.reason == "Exact match."


class TestFuzzyTiers:
    def test_high_similarity_is_match(self):
        # One letter different. token_set_ratio is high.
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Old Tom Distilery"),
        )
        # token_set_ratio for one-character typo on a long string is in the
        # 95+ band; this should be a Match with a similarity note.
        assert result.status is FieldStatus.MATCH
        assert "similarity" in result.reason.lower()

    def test_partial_similarity_is_needs_review(self):
        # "Old Tom Distilleries" vs "Old Tom Distillery":
        # plural form yields token_set_ratio ~89, in the Needs Review band.
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Old Tom Distilleries"),
        )
        assert result.status is FieldStatus.NEEDS_REVIEW

    def test_low_similarity_is_mismatch(self):
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Acme Soft Drinks"),
        )
        assert result.status is FieldStatus.MISMATCH

    def test_clearly_different_brand_is_mismatch(self):
        # "Old Tom Brewery" vs "Old Tom Distillery" scores ~67 - below the
        # Needs Review band. A brewery is not a distillery, so Mismatch is
        # the correct outcome (reviewer can override after seeing evidence).
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Old Tom Brewery"),
        )
        assert result.status is FieldStatus.MISMATCH


class TestConfidencePropagation:
    def test_low_confidence_downgrades_match_to_needs_review(self):
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Old Tom Distillery", confidence=Confidence.LOW),
        )
        assert result.status is FieldStatus.NEEDS_REVIEW
        assert "low" in result.reason.lower()

    def test_uncertain_confidence_downgrades_match(self):
        result = compare_field(
            field=FieldName.BRAND_NAME,
            expected="Old Tom Distillery",
            extracted=_extracted("Old Tom Distillery", confidence=Confidence.UNCERTAIN),
        )
        assert result.status is FieldStatus.NEEDS_REVIEW


class TestMissingAndAbsent:
    def test_extracted_missing(self):
        result = compare_field(
            field=FieldName.BOTTLER,
            expected="Old Tom Co., Frankfort, KY",
            extracted=_extracted(None, confidence=Confidence.UNCERTAIN),
        )
        assert result.status is FieldStatus.MISSING

    def test_no_expected_value_with_extracted_text(self):
        result = compare_field(
            field=FieldName.COUNTRY_OF_ORIGIN,
            expected=None,
            extracted=_extracted("USA"),
        )
        # Reviewer-driven: nothing to compare against, surface for review.
        assert result.status is FieldStatus.NEEDS_REVIEW

    def test_no_expected_value_and_no_extracted(self):
        result = compare_field(
            field=FieldName.COUNTRY_OF_ORIGIN,
            expected=None,
            extracted=_extracted(None, confidence=Confidence.UNCERTAIN),
        )
        assert result.status is FieldStatus.MISSING

    def test_empty_string_expected_treated_as_unsupplied(self):
        """Frontend forms send '' for blank optional fields; treat as None.

        Without this coercion, an empty expected would fall through to the
        comparison branch and produce a spurious Mismatch / Missing row
        against whatever was extracted (or against an empty string),
        misleading the reviewer.
        """
        result = compare_field(
            field=FieldName.CLASS_TYPE,
            expected="",
            extracted=_extracted("Bourbon Whiskey"),
        )
        # Behaves the same as expected=None: NEEDS_REVIEW because something
        # was extracted but no expected value was supplied to compare against.
        assert result.status is FieldStatus.NEEDS_REVIEW
        assert result.expected is None

    def test_whitespace_only_expected_treated_as_unsupplied(self):
        result = compare_field(
            field=FieldName.CLASS_TYPE,
            expected="   \t  ",
            extracted=_extracted(None, confidence=Confidence.UNCERTAIN),
        )
        assert result.status is FieldStatus.MISSING
        assert result.expected is None
