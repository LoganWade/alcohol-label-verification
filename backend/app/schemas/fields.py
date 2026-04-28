"""Schemas for expected and extracted field values.

These are the data contracts between the user-supplied application data, the
extraction pipeline, and the comparison stage. The set of supported fields is
intentionally small and explicit; adding a new field requires adding it here
in one place.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import Confidence
from app.schemas.common import BoundingBox


class FieldName(StrEnum):
    """The fixed set of fields the prototype compares.

    These names are reused as keys in API requests, in extracted output, and
    in comparison results. A reviewer always sees the same field labels in
    the same order.
    """

    BRAND_NAME = "brand_name"
    CLASS_TYPE = "class_type"
    ALCOHOL_CONTENT = "alcohol_content"
    NET_CONTENTS = "net_contents"
    BOTTLER = "bottler"
    COUNTRY_OF_ORIGIN = "country_of_origin"
    WARNING = "warning"


class ExpectedFields(BaseModel):
    """Expected application data supplied by the reviewer.

    All fields are optional. ``None`` means the reviewer did not supply a
    value; for required fields like the warning the validator falls back to
    the statutory default.
    """

    model_config = ConfigDict(extra="forbid")

    brand_name: str | None = None
    class_type: str | None = None
    alcohol_content: str | None = None
    net_contents: str | None = None
    bottler: str | None = None
    country_of_origin: str | None = None
    warning: str | None = None


class ExtractedField(BaseModel):
    """A single extracted field with provenance and confidence.

    ``raw_text`` is the immutable OCR-derived value preserved verbatim for
    display and audit. ``normalized_text`` is the comparator's working copy
    and may differ (case, whitespace, punctuation).
    """

    model_config = ConfigDict(frozen=True)

    field: FieldName
    raw_text: str | None = None
    normalized_text: str | None = None
    evidence_bbox: BoundingBox | None = None
    confidence: Confidence = Confidence.UNCERTAIN
    notes: str | None = Field(
        default=None,
        description="Optional human-readable note from the extractor (e.g. unit conversion).",
    )


class ExtractedFields(BaseModel):
    """All fields extracted from a label image."""

    model_config = ConfigDict(extra="forbid")

    brand_name: ExtractedField
    class_type: ExtractedField
    alcohol_content: ExtractedField
    net_contents: ExtractedField
    bottler: ExtractedField
    country_of_origin: ExtractedField
    warning: ExtractedField

    def by_name(self, name: FieldName) -> ExtractedField:
        return getattr(self, name.value)
