"""Public API schemas for the analyze endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import Confidence, FieldStatus, ImageQuality, ReviewStatus
from app.schemas.common import BoundingBox
from app.schemas.fields import ExtractedFields, FieldName
from app.schemas.pipeline import StageTimings


class FieldComparison(BaseModel):
    """One row in the reviewer's results table.

    The shape mirrors what the UI renders: the expected value, the raw
    extracted value (preserved verbatim from OCR), the normalized value used
    for matching, the resulting status from the fixed vocabulary, a
    plain-language reason, and the bounding box for the evidence panel.
    """

    model_config = ConfigDict(frozen=True)

    field: FieldName
    expected: str | None
    found_raw: str | None
    found_normalized: str | None
    status: FieldStatus
    reason: str
    confidence: Confidence
    evidence_bbox: BoundingBox | None = None


class WarningValidation(BaseModel):
    """Result of the dedicated Government Warning validator.

    Independent of FieldComparison because the warning has its own structural
    rules (caps header, exact wording) that the generic comparator does not
    enforce.
    """

    model_config = ConfigDict(frozen=True)

    status: FieldStatus
    header_caps_ok: bool
    wording_match: bool
    raw_text: str | None
    expected_text: str
    reason: str
    evidence_bbox: BoundingBox | None = None


class ReviewSummary(BaseModel):
    """Top-of-results headline. One status, one sentence."""

    model_config = ConfigDict(frozen=True)

    status: ReviewStatus
    headline: str


class ProcessingMetadata(BaseModel):
    """Trust signals shown in the UI footer of the results screen."""

    model_config = ConfigDict(frozen=True)

    elapsed_ms: int = Field(ge=0)
    image_quality: ImageQuality
    stages_ms: StageTimings
    ocr_provider: str
    version: str


class AnalyzeResponse(BaseModel):
    """Full /analyze response."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    summary: ReviewSummary
    extracted_fields: ExtractedFields
    field_comparisons: list[FieldComparison]
    warning_validation: WarningValidation
    processing: ProcessingMetadata
    limitations: list[str] = Field(
        default_factory=lambda: [
            "This tool assists review and does not replace reviewer judgment.",
        ]
    )


class AnalyzeError(BaseModel):
    """Structured error envelope. Frontend renders code + recovery hint."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    recovery_hint: str | None = None
