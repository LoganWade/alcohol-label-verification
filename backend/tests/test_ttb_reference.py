"""Pipeline tests for TTB public reference label images.

These tests assert that the pipeline runs without error and returns a
structured, non-empty result for each of the three TTB reference labels.

We do NOT assert that specific fields return 'Match' because the stub OCR
provider returns canned data that does not correspond to the actual label
content — exact match assertions would be brittle and misleading.

What we do assert:
  - The pipeline completes without raising an exception
  - The result has the correct top-level shape (review_id, summary, …)
  - At least the five required fields are present in field_comparisons
  - All status values come from the fixed vocabulary (no invented strings)
  - The result is non-empty (field_comparisons has at least 1 entry)

When a real OCR provider is available, test authors can add a
``@pytest.mark.real_ocr`` variant that asserts richer outcomes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.constants import FieldStatus, ReviewStatus
from app.schemas.fields import ExpectedFields
from app.services.pipeline import analyze

SAMPLE_DATA = Path(__file__).resolve().parent.parent.parent / "sample_data"

TTB_SAMPLE_IDS = [
    "ttb_wine_reference",
    "ttb_table_wine_reference",
    "ttb_beer_reference",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_ttb_sample(sample_id: str) -> tuple[bytes, ExpectedFields]:
    label_path = SAMPLE_DATA / "labels" / f"{sample_id}.png"
    fields_path = SAMPLE_DATA / "expected_fields" / f"{sample_id}.json"
    image_bytes = label_path.read_bytes()
    raw = json.loads(fields_path.read_text(encoding="utf-8"))
    return image_bytes, ExpectedFields.model_validate(raw)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTTBReferencePipelineRuns:
    """The pipeline must complete for every TTB reference label."""

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_pipeline_completes_without_error(self, sample_id: str):
        """Running the pipeline must not raise any exception."""
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert result is not None

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_result_has_review_id(self, sample_id: str):
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert isinstance(result.review_id, str)
        assert result.review_id.startswith("rev_")

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_result_has_non_empty_field_comparisons(self, sample_id: str):
        """The result must contain at least one field comparison."""
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert len(result.field_comparisons) >= 1, (
            f"[{sample_id}] expected at least 1 field comparison, got 0"
        )

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_result_has_required_fields(self, sample_id: str):
        """The five required fields must each have a comparison row."""
        required = {
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "bottler",
        }
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        found = {fc.field.value for fc in result.field_comparisons}
        missing = required - found
        assert not missing, (
            f"[{sample_id}] missing required field comparisons: {missing}"
        )

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_status_vocabulary_is_valid(self, sample_id: str):
        """Every status value must come from the fixed vocabulary."""
        allowed_field = {s.value for s in FieldStatus}
        allowed_review = {s.value for s in ReviewStatus}
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        for fc in result.field_comparisons:
            assert fc.status.value in allowed_field, (
                f"[{sample_id}] field {fc.field!r}: invalid status {fc.status!r}"
            )
        assert result.warning_validation.status.value in allowed_field
        assert result.summary.status.value in allowed_review

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_warning_validation_present(self, sample_id: str):
        """Warning validation result must always be present."""
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert result.warning_validation is not None

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_summary_has_headline(self, sample_id: str):
        """Summary must carry a non-empty headline string."""
        image_bytes, expected = _load_ttb_sample(sample_id)
        result = analyze(image_bytes=image_bytes, expected=expected)
        assert isinstance(result.summary.headline, str)
        assert len(result.summary.headline) > 0


# ---------------------------------------------------------------------------
# Provenance — verify images and fields exist on disk
# ---------------------------------------------------------------------------

class TestTTBReferenceFilesExist:
    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_label_png_exists(self, sample_id: str):
        path = SAMPLE_DATA / "labels" / f"{sample_id}.png"
        assert path.exists(), f"Missing label image: {path}"

    @pytest.mark.parametrize("sample_id", TTB_SAMPLE_IDS)
    def test_expected_fields_json_exists(self, sample_id: str):
        path = SAMPLE_DATA / "expected_fields" / f"{sample_id}.json"
        assert path.exists(), f"Missing expected fields: {path}"

    def test_provenance_md_exists(self):
        path = SAMPLE_DATA / "labels" / "PROVENANCE.md"
        assert path.exists(), "PROVENANCE.md is missing from sample_data/labels/"

    def test_provenance_md_mentions_all_ttb_samples(self):
        path = SAMPLE_DATA / "labels" / "PROVENANCE.md"
        content = path.read_text(encoding="utf-8")
        for sample_id in TTB_SAMPLE_IDS:
            # The filename should appear in PROVENANCE.md
            assert f"{sample_id}.png" in content, (
                f"PROVENANCE.md does not mention {sample_id}.png"
            )
