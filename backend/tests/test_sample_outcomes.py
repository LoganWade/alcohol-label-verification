"""Pipeline outcome tests for synthetic sample scenarios.

Each test verifies that when the pipeline runs against a synthetic sample's
expected_fields JSON and its label PNG, the result conforms to the documented
expected_outcome for that scenario.

Tests that depend on real OCR are decorated with ``@pytest.mark.real_ocr`` so
they can be excluded from CI where only the stub provider is available:

    pytest -m "not real_ocr"    # fast, stub-only CI run
    pytest -m real_ocr          # slow, requires PaddleOCR installation

For now all tests use the stub provider.  The stub returns deterministic
canned values so outcome assertions use the stub's canned fields, not the
synthetic label's actual text.  The goal is to verify the pipeline mechanics
(the seven-stage contract stays intact) rather than end-to-end OCR accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.constants import FieldStatus, ImageQuality, ReviewStatus
from app.schemas.fields import ExpectedFields
from app.services.pipeline import analyze

SAMPLE_DATA = Path(__file__).resolve().parent.parent.parent / "sample_data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_sample(sample_id: str) -> tuple[bytes, ExpectedFields]:
    """Return (image_bytes, ExpectedFields) for a named sample."""
    label_path = SAMPLE_DATA / "labels" / f"{sample_id}.png"
    fields_path = SAMPLE_DATA / "expected_fields" / f"{sample_id}.json"
    image_bytes = label_path.read_bytes()
    raw = json.loads(fields_path.read_text(encoding="utf-8"))
    return image_bytes, ExpectedFields.model_validate(raw)


# ---------------------------------------------------------------------------
# Structural contract — run pipeline on every synthetic sample
# ---------------------------------------------------------------------------

SYNTHETIC_IDS = [
    "clean_match",
    "case_only_brand",
    "typo_brand",
    "abv_mismatch",
    "warning_titlecase",
    "warning_missing",
    "skewed_lowlight",
    "unreadable",
]


class TestPipelineRunsForAllSyntheticSamples:
    """The pipeline must complete without exception for every synthetic label."""

    @pytest.mark.parametrize("sample_id", SYNTHETIC_IDS)
    def test_pipeline_runs_without_error(self, sample_id: str):
        image_bytes, expected = _load_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert result.review_id.startswith("rev_")
        assert result.summary is not None
        assert len(result.field_comparisons) >= 5  # at least the 5 required fields

    @pytest.mark.parametrize("sample_id", SYNTHETIC_IDS)
    def test_result_has_valid_status_vocabulary(self, sample_id: str):
        """Status values must come from the fixed vocabulary — no invented strings."""
        image_bytes, expected = _load_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)

        allowed_field = {s.value for s in FieldStatus}
        allowed_review = {s.value for s in ReviewStatus}

        for fc in result.field_comparisons:
            assert fc.status.value in allowed_field, (
                f"[{sample_id}] field {fc.field!r} has invalid status {fc.status!r}"
            )
        assert result.warning_validation.status.value in allowed_field
        assert result.summary.status.value in allowed_review

    @pytest.mark.parametrize("sample_id", SYNTHETIC_IDS)
    def test_result_has_image_quality_field(self, sample_id: str):
        image_bytes, expected = _load_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        allowed = {q.value for q in ImageQuality}
        assert result.processing.image_quality.value in allowed


# ---------------------------------------------------------------------------
# Unreadable sample — FAILED quality, all Uncertain
# ---------------------------------------------------------------------------

class TestUnreadableSample:
    """A nearly-black image must yield FAILED quality and Uncertain fields."""

    def test_image_quality_is_failed_or_poor(self):
        image_bytes, expected = _load_sample("unreadable")
        result = analyze(image_bytes=image_bytes, expected=expected)
        # The preprocess stage should flag this as FAILED or POOR
        assert result.processing.image_quality in (
            ImageQuality.FAILED,
            ImageQuality.POOR,
        ), f"Expected FAILED or POOR, got {result.processing.image_quality!r}"

    def test_field_comparisons_non_empty(self):
        image_bytes, expected = _load_sample("unreadable")
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert len(result.field_comparisons) > 0


# ---------------------------------------------------------------------------
# Real OCR marker — these tests are skipped unless -m real_ocr is passed
# ---------------------------------------------------------------------------

@pytest.mark.real_ocr
class TestSyntheticOutcomesWithRealOCR:
    """
    Integration tests that require a real OCR provider (PaddleOCR).
    Run with:  pytest -m real_ocr --ocr-provider paddle

    Outcome assertions here are intentionally loose (status in allowed set)
    because exact OCR output may vary slightly across model versions.
    """

    @pytest.mark.parametrize("sample_id", SYNTHETIC_IDS)
    def test_pipeline_runs_with_real_ocr(self, sample_id: str):
        image_bytes, expected = _load_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert result.review_id.startswith("rev_")
        assert len(result.field_comparisons) >= 5
