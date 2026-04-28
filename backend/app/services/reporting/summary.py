"""Compose the top-of-results summary from per-field outcomes."""

from __future__ import annotations

from app.core.constants import FieldStatus, ReviewStatus
from app.schemas.review import FieldComparison, ReviewSummary, WarningValidation


def _count(statuses: list[FieldStatus], target: FieldStatus) -> int:
    return sum(1 for s in statuses if s is target)


def build_summary(
    comparisons: list[FieldComparison],
    warning: WarningValidation,
) -> ReviewSummary:
    """Roll up per-field statuses into a single overall status + headline.

    Ordering of severity (worst wins):
      Mismatch  >  Needs Review  >  Uncertain  >  Missing  >  Match

    The warning result is included in this rollup; a warning failure cannot
    be hidden by passing fields.
    """

    statuses: list[FieldStatus] = [c.status for c in comparisons] + [warning.status]
    total = len(statuses)
    matches = _count(statuses, FieldStatus.MATCH)
    mismatches = _count(statuses, FieldStatus.MISMATCH)
    needs_review = _count(statuses, FieldStatus.NEEDS_REVIEW)
    missing = _count(statuses, FieldStatus.MISSING)
    uncertain = _count(statuses, FieldStatus.UNCERTAIN)

    if mismatches > 0 or missing > 0:
        overall = ReviewStatus.MISMATCH
    elif needs_review > 0 or uncertain > 0:
        overall = ReviewStatus.NEEDS_REVIEW
    else:
        overall = ReviewStatus.PASS

    parts: list[str] = [f"{matches} of {total} fields match."]
    if mismatches:
        parts.append(f"{mismatches} mismatch{'es' if mismatches != 1 else ''}.")
    if missing:
        parts.append(f"{missing} missing.")
    if needs_review:
        parts.append(
            f"{needs_review} need{'s' if needs_review == 1 else ''} review."
        )
    if uncertain:
        parts.append(f"{uncertain} uncertain.")

    return ReviewSummary(status=overall, headline=" ".join(parts))
