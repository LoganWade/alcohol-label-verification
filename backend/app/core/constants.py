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
# Batch / application workflow vocabulary
# ---------------------------------------------------------------------------
# Application processing state — lifecycle of the OCR pipeline run for one
# application within a batch. Independent of the analyst's decision.
class ApplicationProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# Analyst-facing workflow status — what the human did about the application.
# Layered on top of the analysis result's ReviewStatus, never collapsed.
# See docs/tradeoffs.md "Workflow status vocabulary".
class WorkflowStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CORRECTION = "needs_correction"


# Image attribution within an application (TTB Step 3 of 3 attachment types).
class ImageAttribution(StrEnum):
    FRONT = "front"
    BACK = "back"
    NECK = "neck"
    BODY = "body"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Comparison thresholds
# ---------------------------------------------------------------------------
# rapidfuzz `fuzz.ratio` thresholds (0-100) for the generic field comparator.
# Tunable here, nowhere else. Tier 3 in services.validation.comparison; Tier 2
# (word-set equality) already absorbs formatting-only differences before this
# runs, so any score below FUZZY_MATCH_THRESHOLD reflects a real word-level
# edit and deserves reviewer eyes.
FUZZY_MATCH_THRESHOLD = 98
FUZZY_NEEDS_REVIEW_THRESHOLD = 80

# Separate threshold for the dedicated Government Warning validator. The
# warning is a long statutory paragraph (~55 words) compared with
# `fuzz.token_set_ratio`, which is forgiving of word-order and whitespace
# but penalizes substantive wording differences. 95 is the historical sweet
# spot: tight enough to catch missing or rewritten clauses, loose enough that
# OCR noise on a single line doesn't tank the whole paragraph score.
# Kept distinct from FUZZY_MATCH_THRESHOLD so the per-field comparator can
# be tuned without dragging the warning validator with it.
WARNING_WORDING_THRESHOLD = 95

# OCR token confidence (0.0-1.0) below which we propagate uncertainty by
# downgrading a Match to Needs Review.
LOW_CONFIDENCE_DOWNGRADE_THRESHOLD = 0.60

# Minimum per-field confidence required for an application to be eligible
# for bulk-approve. See docs/tradeoffs.md "Bulk-approve clean matches".
# Conservative by design: medium-confidence Matches still require a human.
BULK_APPROVE_REQUIRES_CONFIDENCE: tuple[Confidence, ...] = (Confidence.HIGH,)


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
# The frontend owns its own "long running" threshold (see
# frontend/src/features/review/ProcessingSection.tsx — LONG_RUNNING_MS) so
# the UI can update its progress hint without a round-trip. There's no
# backend consumer for a separate threshold; if one is ever added, define
# it here rather than re-introducing dead code.
TARGET_TOTAL_MS = 5000
