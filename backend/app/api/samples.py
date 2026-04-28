"""Samples API: read-only access to demo label fixtures.

Three endpoints:
  GET /api/v1/samples                    → list all samples (SampleSummary[])
  GET /api/v1/samples/{id}/image         → raw PNG bytes
  GET /api/v1/samples/{id}/expected-fields → ExpectedFields JSON object

All 404 responses use the same AnalyzeError envelope shape as reviews.py so
the frontend can use a single error handler.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.core.settings import settings
from app.schemas.fields import ExpectedFields
from app.schemas.review import AnalyzeError

router = APIRouter(prefix="/samples", tags=["samples"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SampleProvenance = Literal["synthetic", "public_ttb_reference"]


class SampleSummary(BaseModel):
    """Lightweight sample descriptor returned by the list endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str
    expected_outcome: str
    provenance: SampleProvenance


class SampleManifestEntry(SampleSummary):
    """Full manifest row (superset of SampleSummary — kept internal)."""

    model_config = ConfigDict(frozen=True)

    image_path: str
    expected_fields_path: str
    source_url: str | None = None


# ---------------------------------------------------------------------------
# Manifest loader (cached for the lifetime of the process)
# ---------------------------------------------------------------------------

def _error(code: str, message: str, recovery: str | None = None) -> AnalyzeError:
    return AnalyzeError(code=code, message=message, recovery_hint=recovery)


@lru_cache(maxsize=1)
def _load_manifest() -> list[SampleManifestEntry]:
    manifest_path = Path(settings.samples_dir) / "manifest.json"
    if not manifest_path.exists():
        return []
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [SampleManifestEntry(**entry) for entry in raw]


def _get_entry(sample_id: str) -> SampleManifestEntry:
    manifest = _load_manifest()
    for entry in manifest:
        if entry.id == sample_id:
            return entry
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_error(
            code="sample_not_found",
            message=f"No sample with id {sample_id!r} exists.",
            recovery="Check the sample id and try again.",
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[SampleSummary],
    summary="List all demo samples",
)
def list_samples() -> list[SampleSummary]:
    """Return all available demo samples ordered as defined in manifest.json."""
    return [SampleSummary(**e.model_dump()) for e in _load_manifest()]


@router.get(
    "/{sample_id}/image",
    summary="Fetch sample label image (PNG)",
    responses={404: {"model": AnalyzeError}},
)
def get_sample_image(sample_id: str) -> FileResponse:
    """Return the raw PNG bytes for a sample label."""
    entry = _get_entry(sample_id)
    image_path = Path(settings.samples_dir) / entry.image_path
    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error(
                code="sample_image_missing",
                message=f"Image file for sample {sample_id!r} is not present on disk.",
                recovery="Re-run scripts/generate_samples.py to regenerate sample data.",
            ).model_dump(),
        )
    return FileResponse(str(image_path), media_type="image/png")


@router.get(
    "/{sample_id}/expected-fields",
    response_model=ExpectedFields,
    summary="Fetch sample expected fields",
    responses={404: {"model": AnalyzeError}},
)
def get_sample_expected_fields(sample_id: str) -> ExpectedFields:
    """Return the pre-filled ExpectedFields for a demo sample."""
    entry = _get_entry(sample_id)
    fields_path = Path(settings.samples_dir) / entry.expected_fields_path
    if not fields_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error(
                code="sample_fields_missing",
                message=f"Expected-fields file for sample {sample_id!r} is not present on disk.",
                recovery="Re-run scripts/generate_samples.py to regenerate sample data.",
            ).model_dump(),
        )
    raw = json.loads(fields_path.read_text(encoding="utf-8"))
    return ExpectedFields.model_validate(raw)
