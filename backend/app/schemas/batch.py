"""Public API schemas for the batch-upload endpoints.

Three resource shapes are exposed:

- ``Batch``: a single submission by an importer (header + summary counts).
- ``Application``: one COLA application within a batch (importer-stated
  fields, processing/workflow status, optional analyze response).
- ``LabelImage``: one uploaded image attached to an application.

The ``AnalyzeResponse`` from the existing ``/analyze`` flow is reused
verbatim as the embedded analysis payload - no new comparison shape.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import (
    ApplicationProcessingStatus,
    ImageAttribution,
    WorkflowStatus,
)
from app.schemas.review import AnalyzeError, AnalyzeResponse

# Lightweight email shape check. We intentionally do not pull in
# ``email-validator`` (the package Pydantic's ``EmailStr`` requires) for the
# prototype - the importer email is informational only and is never used to
# send mail. The pattern matches "<non-space-non-at>@<non-space-non-at>.<tld>".
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email_shape(value: str) -> str:
    value = value.strip()
    if not _EMAIL_RE.match(value):
        raise ValueError("importer_email must look like an email address")
    if len(value) > 254:
        raise ValueError("importer_email is too long")
    return value


class LabelImage(BaseModel):
    """One image attached to an application."""

    model_config = ConfigDict(frozen=True)

    id: str
    filename: str
    attribution: ImageAttribution
    is_primary: bool
    byte_size: int = Field(ge=0)
    content_type: str


class ApplicationFields(BaseModel):
    """Importer-stated COLA fields (TTB Step 2 of 3, prototype subset).

    Mirrors a row of the manifest CSV. All fields except ``serial_number``
    are optional; ``None`` means "not on the label" rather than "unknown".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    serial_number: str = Field(min_length=1, max_length=64)
    brand_name: str | None = None
    fanciful_name: str | None = None
    class_type: str | None = None
    alcohol_content: str | None = None
    net_contents: str | None = None
    bottler: str | None = None
    country_of_origin: str | None = None


class Application(BaseModel):
    """One COLA application within a batch."""

    model_config = ConfigDict(extra="forbid")

    id: str
    batch_id: str
    fields: ApplicationFields
    processing_status: ApplicationProcessingStatus
    workflow_status: WorkflowStatus
    images: list[LabelImage]
    analyze: AnalyzeResponse | None = None
    error: AnalyzeError | None = None
    created_at: str
    processed_at: str | None = None
    decided_at: str | None = None
    decided_note: str | None = None


class BatchSummaryCounts(BaseModel):
    """Aggregate counts across applications in a batch."""

    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    processing: int = Field(ge=0)
    done: int = Field(ge=0)
    failed: int = Field(ge=0)
    approved: int = Field(ge=0)
    rejected: int = Field(ge=0)
    needs_correction: int = Field(ge=0)


class Batch(BaseModel):
    """A batch submission. The list view returns these without applications;
    the detail view embeds the application list."""

    model_config = ConfigDict(extra="forbid")

    id: str
    importer_name: str
    importer_email: str
    note: str | None
    counts: BatchSummaryCounts
    created_at: str

    @field_validator("importer_email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validate_email_shape(value)


class BatchDetail(Batch):
    """Batch + embedded applications."""

    applications: list[Application]


# ---------------------------------------------------------------------------
# Submission + decision request bodies
# ---------------------------------------------------------------------------
class BatchSubmissionMeta(BaseModel):
    """The non-file portion of POST /batches.

    Submitted as a JSON-encoded form field alongside the manifest CSV and
    image files (multipart/form-data).
    """

    model_config = ConfigDict(extra="forbid")

    importer_name: str = Field(min_length=1, max_length=200)
    importer_email: str = Field(min_length=3, max_length=254)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("importer_email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validate_email_shape(value)


class WorkflowDecision(BaseModel):
    """PUT /applications/{id}/decision body."""

    model_config = ConfigDict(extra="forbid")

    workflow_status: WorkflowStatus
    note: str | None = Field(default=None, max_length=2000)


class BulkApproveRequest(BaseModel):
    """POST /batches/{id}/bulk-approve body.

    Empty for now (the eligibility rule lives server-side in constants),
    but kept as a body for forward-compatibility with future filters.
    """

    model_config = ConfigDict(extra="forbid")


class BulkApproveResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
