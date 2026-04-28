"""Inter-stage pipeline schemas.

These are the typed contracts between extraction stages. They are not part of
the public API surface but are exercised by unit tests so a stage swap (e.g.
replacing the stub OCR provider with PaddleOCR) cannot silently change the
shape of data flowing downstream.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ImageQuality


class ImageQualityReport(BaseModel):
    """Output of the preprocess stage. Uncertainty propagates from here."""

    model_config = ConfigDict(frozen=True)

    quality: ImageQuality
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    estimated_skew_degrees: float = 0.0
    blur_score: float = Field(default=0.0, ge=0.0)
    contrast_score: float = Field(default=0.0, ge=0.0)
    notes: list[str] = Field(default_factory=list)


class PreprocessOutput(BaseModel):
    """Preprocess stage result.

    ``processed_image`` carries the PNG-encoded preprocessed image bytes that
    the OCR stage consumes directly.  The ``repr=False`` suppresses the field
    from ``__repr__`` so large binary payloads do not bloat log lines.
    """

    model_config = ConfigDict(frozen=True)

    quality_report: ImageQualityReport
    processed_image: bytes = Field(repr=False)


class StageTimings(BaseModel):
    """Per-stage elapsed milliseconds. Surfaced to reviewers as a trust signal."""

    model_config = ConfigDict(extra="forbid")

    preprocess_ms: int = 0
    ocr_ms: int = 0
    region_attribution_ms: int = 0
    field_extraction_ms: int = 0
    comparison_ms: int = 0
    warning_validation_ms: int = 0
    reporting_ms: int = 0

    @property
    def total_ms(self) -> int:
        return (
            self.preprocess_ms
            + self.ocr_ms
            + self.region_attribution_ms
            + self.field_extraction_ms
            + self.comparison_ms
            + self.warning_validation_ms
            + self.reporting_ms
        )
