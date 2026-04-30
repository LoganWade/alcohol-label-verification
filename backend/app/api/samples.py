"""Samples API: read-only access to demo label fixtures.

Single-image samples (used by ReviewNewPage):
  GET /api/v1/samples                       → list (SampleSummary[])
  GET /api/v1/samples/{id}/image            → raw PNG bytes
  GET /api/v1/samples/{id}/expected-fields  → ExpectedFields JSON

Batch samples (used by BatchUploadPage to pre-fill the importer form):
  GET /api/v1/samples/batch                       → list (BatchSampleSummary[])
  GET /api/v1/samples/batch/{id}/manifest         → raw manifest CSV bytes
  GET /api/v1/samples/batch/{id}/image/{filename} → raw PNG bytes

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


class BatchSampleSummary(BaseModel):
    """Lightweight batch-sample descriptor for the home-page card."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str
    expected_outcome: str
    provenance: SampleProvenance
    importer_name: str
    importer_email: str
    note: str | None = None
    image_filenames: tuple[str, ...]


class BatchSampleManifestEntry(BaseModel):
    """Full batch-sample manifest entry (kept internal)."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str
    expected_outcome: str
    provenance: SampleProvenance
    importer_name: str
    importer_email: str
    note: str | None = None
    manifest_path: str
    images_dir: str


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


# ---------------------------------------------------------------------------
# Batch sample loader + endpoints
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_batch_manifest() -> list[BatchSampleManifestEntry]:
    """Load batch-sample descriptors from sample_data/batch-manifest.json."""
    manifest_path = Path(settings.samples_dir) / "batch-manifest.json"
    if not manifest_path.exists():
        return []
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [BatchSampleManifestEntry(**entry) for entry in raw]


def _get_batch_entry(sample_id: str) -> BatchSampleManifestEntry:
    for entry in _load_batch_manifest():
        if entry.id == sample_id:
            return entry
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_error(
            code="batch_sample_not_found",
            message=f"No batch sample with id {sample_id!r} exists.",
            recovery="Check the sample id; see sample_data/batch-manifest.json.",
        ).model_dump(),
    )


def _list_batch_image_filenames(entry: BatchSampleManifestEntry) -> tuple[str, ...]:
    """Return the manifest's image_filename column values, in order, deduped."""
    import csv

    manifest_path = Path(settings.samples_dir) / entry.manifest_path
    if not manifest_path.exists():
        return ()
    seen: set[str] = set()
    out: list[str] = []
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("image_filename") or "").strip()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return tuple(out)


def _safe_image_path(entry: BatchSampleManifestEntry, filename: str) -> Path:
    """Resolve <samples_dir>/<images_dir>/<filename>, blocking traversal."""
    safe_name = Path(filename).name  # strip any directory components
    if safe_name != filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error(
                code="invalid_filename",
                message="Filename must not contain path separators.",
            ).model_dump(),
        )
    return Path(settings.samples_dir) / entry.images_dir / safe_name


@router.get(
    "/batch",
    response_model=list[BatchSampleSummary],
    summary="List all batch-upload demo samples",
)
def list_batch_samples() -> list[BatchSampleSummary]:
    """Return all available batch-upload demos."""
    out: list[BatchSampleSummary] = []
    for entry in _load_batch_manifest():
        out.append(
            BatchSampleSummary(
                id=entry.id,
                title=entry.title,
                description=entry.description,
                expected_outcome=entry.expected_outcome,
                provenance=entry.provenance,
                importer_name=entry.importer_name,
                importer_email=entry.importer_email,
                note=entry.note,
                image_filenames=_list_batch_image_filenames(entry),
            )
        )
    return out


@router.get(
    "/batch/{sample_id}/manifest",
    summary="Fetch batch sample manifest CSV",
    responses={404: {"model": AnalyzeError}},
)
def get_batch_sample_manifest(sample_id: str) -> FileResponse:
    """Return the raw manifest CSV bytes for a batch sample."""
    entry = _get_batch_entry(sample_id)
    manifest_path = Path(settings.samples_dir) / entry.manifest_path
    if not manifest_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error(
                code="batch_sample_manifest_missing",
                message=(
                    f"Manifest file for batch sample {sample_id!r} "
                    "is not present on disk."
                ),
                recovery="Verify sample_data/batch-manifest.json paths.",
            ).model_dump(),
        )
    return FileResponse(
        str(manifest_path),
        media_type="text/csv",
        filename=manifest_path.name,
    )


@router.get(
    "/batch/{sample_id}/image/{filename}",
    summary="Fetch a batch sample image (PNG)",
    responses={404: {"model": AnalyzeError}},
)
def get_batch_sample_image(sample_id: str, filename: str) -> FileResponse:
    """Return the raw PNG bytes for a single image in a batch sample."""
    entry = _get_batch_entry(sample_id)
    image_path = _safe_image_path(entry, filename)
    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error(
                code="batch_sample_image_missing",
                message=(
                    f"Image {filename!r} is not present in batch sample "
                    f"{sample_id!r}."
                ),
                recovery="Verify the manifest's image_filename column.",
            ).model_dump(),
        )
    return FileResponse(str(image_path), media_type="image/png")
