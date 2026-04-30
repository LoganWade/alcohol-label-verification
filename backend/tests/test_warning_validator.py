"""Unit tests for the dedicated Government Warning validator.

Covers the four primary return states: Match, Mismatch (header or wording),
Missing, Uncertain.
"""

from __future__ import annotations

from app.core.constants import (
    DEFAULT_GOVERNMENT_WARNING,
    Confidence,
    FieldStatus,
)
from app.schemas.common import BoundingBox
from app.schemas.fields import ExtractedField, FieldName
from app.services.validation.warning_validator import validate_warning


def _warning_field(
    text: str | None,
    confidence: Confidence = Confidence.HIGH,
) -> ExtractedField:
    return ExtractedField(
        field=FieldName.WARNING,
        raw_text=text,
        normalized_text=text,
        evidence_bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10) if text else None,
        confidence=confidence,
    )


class TestMatch:
    def test_correct_warning_matches(self):
        result = validate_warning(_warning_field(DEFAULT_GOVERNMENT_WARNING))
        assert result.status == FieldStatus.MATCH
        assert result.header_caps_ok is True
        assert result.wording_match is True


class TestHeaderCapsRule:
    """Jenny Park's specific concern: title-case header is a failure."""

    def test_title_case_header_fails(self):
        text = (
            "Government Warning: (1) According to the Surgeon General, women "
            "should not drink alcoholic beverages during pregnancy because of "
            "the risk of birth defects. (2) Consumption of alcoholic beverages "
            "impairs your ability to drive a car or operate machinery, and "
            "may cause health problems."
        )
        result = validate_warning(_warning_field(text))
        assert result.status == FieldStatus.MISMATCH
        assert result.header_caps_ok is False
        # Wording itself is correct; only the header format failed.
        assert result.wording_match is True
        assert "all caps" in result.reason.lower()


class TestWordingMismatch:
    def test_reworded_body_fails_even_with_caps_header(self):
        text = (
            "GOVERNMENT WARNING: Drinking alcohol may be bad for you and you "
            "should be careful when operating heavy machinery."
        )
        result = validate_warning(_warning_field(text))
        assert result.status == FieldStatus.MISMATCH
        assert result.header_caps_ok is True
        assert result.wording_match is False


class TestMissing:
    def test_missing_warning_text(self):
        result = validate_warning(_warning_field(None, confidence=Confidence.UNCERTAIN))
        assert result.status == FieldStatus.MISSING
        assert result.header_caps_ok is False
        assert result.wording_match is False


class TestUncertain:
    def test_low_confidence_returns_uncertain(self):
        result = validate_warning(
            _warning_field(DEFAULT_GOVERNMENT_WARNING, confidence=Confidence.LOW)
        )
        assert result.status == FieldStatus.UNCERTAIN
        assert "confidence" in result.reason.lower()


class TestCustomExpectedText:
    def test_custom_expected_text_is_honored(self):
        custom = "GOVERNMENT WARNING: please drink responsibly."
        result = validate_warning(_warning_field(custom), expected_text=custom)
        assert result.status == FieldStatus.MATCH
