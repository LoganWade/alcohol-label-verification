"""
Single source of truth for status vocabulary, comparison thresholds, and the
default Government Warning text.

Per AGENTS.md:
- Status vocabulary is fixed across UI and API. No frontend-only synonyms.
- Comparison thresholds live in one inspectable module so a reviewer can see
  every magic number the system uses by reading one file.
"""

from __future__ import annotations

from enum import StrEnum


# ---------------------------------------------------------------------------
# Fixed status vocabulary
# ---------------------------------------------------------------------------
# Per-field comparison status. The frontend renders these verbatim.
class FieldStatus(StrEnum):
    MATCH = "Match"
    MISMATCH = "Mismatch"
    MISSING = "Missing"
    NEEDS_REVIEW = "Needs Review"
    UNCERTAIN = "Uncertain"


# Overall review summary status.
class ReviewStatus(StrEnum):
    PASS = "Pass"
    MISMATCH = "Mismatch"
    NEEDS_REVIEW = "Needs Review"


# Confidence tiers for OCR / extraction quality.
class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


# Image quality tiers from the preprocess stage.
class ImageQuality(StrEnum):
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Comparison thresholds
# ---------------------------------------------------------------------------
# rapidfuzz token_set_ratio thresholds (0-100). Tunable here, nowhere else.
FUZZY_MATCH_THRESHOLD = 95
FUZZY_NEEDS_REVIEW_THRESHOLD = 85

# OCR token confidence (0.0-1.0) below which we propagate uncertainty by
# downgrading a Match to Needs Review.
LOW_CONFIDENCE_DOWNGRADE_THRESHOLD = 0.60


# ---------------------------------------------------------------------------
# Government Warning
# ---------------------------------------------------------------------------
# 27 CFR 16.21 - the statutory warning text. Used as the default when an
# expected warning is not provided by the caller.
DEFAULT_GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)

# The literal header that must appear in all caps on the label.
GOVERNMENT_WARNING_HEADER = "GOVERNMENT WARNING"


# ---------------------------------------------------------------------------
# Pipeline budgets (advisory; surfaced in processing metadata)
# ---------------------------------------------------------------------------
TARGET_TOTAL_MS = 5000
LONG_RUNNING_THRESHOLD_MS = 8000
