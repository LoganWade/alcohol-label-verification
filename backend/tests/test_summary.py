"""Unit tests for the summary rollup."""

from __future__ import annotations

from app.core.constants import Confidence, FieldStatus, ReviewStatus
from app.schemas.fields import FieldName
from app.schemas.review import FieldComparison, WarningValidation
from app.services.reporting.summary import build_summary


def _comp(field: FieldName, status: FieldStatus) -> FieldComparison:
    return FieldComparison(
        field=field,
        expected="x",
        found_raw="x",
        found_normalized="x",
        status=status,
        reason="",
        confidence=Confidence.HIGH,
    )


def _warning(status: FieldStatus) -> WarningValidation:
    return WarningValidation(
        status=status,
        header_caps_ok=status is FieldStatus.MATCH,
        wording_match=status is FieldStatus.MATCH,
        raw_text="x",
        expected_text="x",
        reason="",
    )


class TestSummary:
    def test_all_matches_is_pass(self):
        comparisons = [_comp(FieldName.BRAND_NAME, FieldStatus.MATCH)]
        warning = _warning(FieldStatus.MATCH)
        summary = build_summary(comparisons, warning)
        assert summary.status is ReviewStatus.PASS

    def test_any_mismatch_is_mismatch(self):
        comparisons = [
            _comp(FieldName.BRAND_NAME, FieldStatus.MATCH),
            _comp(FieldName.ALCOHOL_CONTENT, FieldStatus.MISMATCH),
        ]
        warning = _warning(FieldStatus.MATCH)
        summary = build_summary(comparisons, warning)
        assert summary.status is ReviewStatus.MISMATCH

    def test_warning_mismatch_dominates_passing_fields(self):
        comparisons = [_comp(FieldName.BRAND_NAME, FieldStatus.MATCH)]
        warning = _warning(FieldStatus.MISMATCH)
        summary = build_summary(comparisons, warning)
        assert summary.status is ReviewStatus.MISMATCH

    def test_needs_review_only_is_needs_review(self):
        comparisons = [
            _comp(FieldName.BRAND_NAME, FieldStatus.MATCH),
            _comp(FieldName.CLASS_TYPE, FieldStatus.NEEDS_REVIEW),
        ]
        warning = _warning(FieldStatus.MATCH)
        summary = build_summary(comparisons, warning)
        assert summary.status is ReviewStatus.NEEDS_REVIEW

    def test_uncertain_warning_is_needs_review(self):
        comparisons = [_comp(FieldName.BRAND_NAME, FieldStatus.MATCH)]
        warning = _warning(FieldStatus.UNCERTAIN)
        summary = build_summary(comparisons, warning)
        assert summary.status is ReviewStatus.NEEDS_REVIEW
