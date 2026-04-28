"""End-to-end orchestration of the seven extraction/validation stages.

Each stage is called explicitly with its typed input/output. Per-stage
elapsed time is captured in the response so reviewers see a trust signal
in the UI footer.
"""

from __future__ import annotations

import time
import uuid

from app import __version__
from app.core.constants import Confidence, ImageQuality
from app.core.settings import settings
from app.schemas.fields import ExpectedFields, FieldName
from app.schemas.pipeline import StageTimings
from app.schemas.review import (
    AnalyzeResponse,
    FieldComparison,
    ProcessingMetadata,
)
from app.services.extraction.field_extraction import extract_fields
from app.services.extraction.ocr import get_ocr_provider
from app.services.extraction.preprocess import preprocess
from app.services.reporting.summary import build_summary
from app.services.validation.comparison import compare_field
from app.services.validation.warning_validator import validate_warning


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------
# Confidence downgrade for poor image quality
# ---------------------------------------------------------------------------
_DOWNGRADE_MAP: dict[Confidence, Confidence] = {
    Confidence.HIGH: Confidence.MEDIUM,
    Confidence.MEDIUM: Confidence.LOW,
    # LOW and UNCERTAIN are already at the floor — no further downgrade.
    Confidence.LOW: Confidence.LOW,
    Confidence.UNCERTAIN: Confidence.UNCERTAIN,
}


def _downgrade_comparison_confidence(comparison: FieldComparison) -> FieldComparison:
    """Return a copy of ``comparison`` with confidence downgraded one tier.

    Used when the preprocess stage reports ``POOR`` image quality — per AGENTS.md
    uncertainty must propagate forward rather than asserting false certainty.
    Only HIGH→MEDIUM and MEDIUM→LOW downgrades are applied; LOW and UNCERTAIN
    are already at the floor and are left unchanged.
    """
    new_confidence = _DOWNGRADE_MAP[comparison.confidence]
    if new_confidence == comparison.confidence:
        return comparison  # no change needed — avoid creating an unnecessary copy

    # FieldComparison is frozen; use model_copy to produce an updated instance.
    return comparison.model_copy(update={"confidence": new_confidence})


def _apply_poor_quality_downgrade(
    comparisons: list[FieldComparison],
) -> list[FieldComparison]:
    """Downgrade all comparison confidences by one tier (POOR quality guard)."""
    return [_downgrade_comparison_confidence(c) for c in comparisons]


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def analyze(image_bytes: bytes, expected: ExpectedFields) -> AnalyzeResponse:
    """Run the full pipeline and return the analyze response."""

    timings = StageTimings()

    # --- 1. Preprocess --------------------------------------------------
    t0 = _now_ms()
    preprocess_output = preprocess(image_bytes)
    timings.preprocess_ms = _now_ms() - t0

    # --- 2. OCR ---------------------------------------------------------
    # The OCR provider receives the *preprocessed* image bytes (EXIF-corrected,
    # resized, contrast-normalised) rather than the raw upload. This ensures
    # PaddleOCR sees the same normalised input regardless of the source device.
    t0 = _now_ms()
    provider = get_ocr_provider(settings.ocr_provider)
    tokens = provider.extract(preprocess_output.processed_image)
    timings.ocr_ms = _now_ms() - t0

    # --- 3. Region attribution + 4. Field extraction --------------------
    # Phase 1 collapses these into a single heuristic pass. Phase 2 will
    # split region attribution and structured parsers.
    t0 = _now_ms()
    extracted = extract_fields(tokens)
    timings.field_extraction_ms = _now_ms() - t0

    # --- 5. Comparison --------------------------------------------------
    t0 = _now_ms()
    # Required fields are always compared and always shown. Optional fields
    # (country_of_origin) are only compared when the reviewer supplied an
    # expected value or the label produced an extracted value; otherwise
    # the row is omitted from the response so reviewers don't see noise.
    required_fields: list[FieldName] = [
        FieldName.BRAND_NAME,
        FieldName.CLASS_TYPE,
        FieldName.ALCOHOL_CONTENT,
        FieldName.NET_CONTENTS,
        FieldName.BOTTLER,
    ]
    optional_fields: list[FieldName] = [FieldName.COUNTRY_OF_ORIGIN]

    comparisons: list[FieldComparison] = []
    for name in required_fields:
        comparisons.append(
            compare_field(
                field=name,
                expected=getattr(expected, name.value),
                extracted=extracted.by_name(name),
            )
        )
    for name in optional_fields:
        exp_value = getattr(expected, name.value)
        ext_value = extracted.by_name(name)
        if exp_value is None and ext_value.raw_text is None:
            continue  # nothing to report; reviewer did not request this check
        comparisons.append(
            compare_field(field=name, expected=exp_value, extracted=ext_value)
        )

    # Propagate image-quality uncertainty: if preprocessing flagged POOR
    # quality, downgrade all extracted-field confidences before comparison
    # results are finalised.  This implements the AGENTS.md rule that
    # "uncertainty propagates forward" across the preprocess→extraction
    # boundary.
    if preprocess_output.quality_report.quality is ImageQuality.POOR:
        comparisons = _apply_poor_quality_downgrade(comparisons)

    timings.comparison_ms = _now_ms() - t0

    # --- 6. Warning validation -----------------------------------------
    t0 = _now_ms()
    warning_result = validate_warning(
        extracted=extracted.warning,
        expected_text=expected.warning,
    )
    timings.warning_validation_ms = _now_ms() - t0

    # --- 7. Reporting --------------------------------------------------
    t0 = _now_ms()
    summary = build_summary(comparisons, warning_result)
    processing = ProcessingMetadata(
        elapsed_ms=timings.total_ms,
        image_quality=preprocess_output.quality_report.quality,
        stages_ms=timings,
        ocr_provider=provider.name,
        version=__version__,
    )
    timings.reporting_ms = _now_ms() - t0
    # Reporting timing is captured but not added to the elapsed total to
    # keep elapsed_ms equal to actual user-perceived work. This is a
    # deliberate trade-off documented in tradeoffs.md.

    return AnalyzeResponse(
        review_id=f"rev_{uuid.uuid4().hex[:16]}",
        summary=summary,
        extracted_fields=extracted,
        field_comparisons=comparisons,
        warning_validation=warning_result,
        processing=processing,
    )
