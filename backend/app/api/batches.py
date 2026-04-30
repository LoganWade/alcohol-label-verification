"""Batch upload API.

Endpoints (all under ``/api/v1``):

- ``POST   /batches``                          create a batch (multipart)
- ``GET    /batches``                          list batches with summary counts
- ``GET    /batches/{batch_id}``               batch detail with applications
- ``GET    /applications/{application_id}``    one application + analysis
- ``PUT    /applications/{application_id}/decision``  set workflow status
- ``POST   /batches/{batch_id}/bulk-approve``  approve all clean matches

The POST is the interesting one: it accepts a multipart form with three
parts (a JSON metadata blob, the manifest CSV, and N image files),
validates the manifest, persists the images to the configured storage
directory, creates the batch in SQLite, and queues background processing
for every application.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.core.constants import (
    ApplicationProcessingStatus,
    ImageAttribution,
    WorkflowStatus,
)
from app.core.settings import settings
from app.schemas.batch import (
    Application,
    Batch,
    BatchDetail,
    BatchSubmissionMeta,
    BulkApproveResponse,
    WorkflowDecision,
)
from app.schemas.review import AnalyzeError
from app.services.batch.manifest import ManifestApplication, ManifestError, parse_manifest
from app.services.batch.processor import schedule_processing
from app.services.batch.storage import (
    ApplicationInput,
    ImageInput,
    get_store,
    is_eligible_for_bulk_approve,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batches"])


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------
def _error(code: str, message: str, recovery: str | None = None) -> AnalyzeError:
    return AnalyzeError(code=code, message=message, recovery_hint=recovery)


def _http_error(
    code: str, message: str, recovery: str | None = None, *, http_status: int = 400
) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail=_error(code, message, recovery).model_dump(),
    )


def _manifest_errors_response(errors: tuple[ManifestError, ...]) -> HTTPException:
    """400 response carrying every manifest-level error as data.

    Importers expect to see all problems at once, so we return them as a
    list under ``manifest_errors`` rather than only the first.
    """

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "invalid_manifest",
            "message": (
                f"The manifest has {len(errors)} problem"
                f"{'s' if len(errors) != 1 else ''}. "
                "Fix every row listed below and re-upload."
            ),
            "recovery_hint": (
                "Each entry includes the row number and the column to fix. "
                "Row 0 means a problem with the file itself."
            ),
            "manifest_errors": [
                {
                    "row_number": e.row_number,
                    "column": e.column,
                    "code": e.code,
                    "message": e.message,
                }
                for e in errors
            ],
        },
    )


# ---------------------------------------------------------------------------
# POST /batches  (multipart)
# ---------------------------------------------------------------------------
@router.post(
    "/batches",
    response_model=Batch,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": AnalyzeError},
        413: {"model": AnalyzeError},
        415: {"model": AnalyzeError},
    },
)
async def create_batch(
    background_tasks: BackgroundTasks,
    meta: str = Form(
        ...,
        description=(
            "JSON-encoded BatchSubmissionMeta with importer name, email, "
            "and optional note."
        ),
    ),
    manifest: UploadFile = File(
        ...,
        description="CSV manifest (UTF-8) describing each application.",
    ),
    images: list[UploadFile] = File(
        ...,
        description="One file per row in the manifest's image_filename column.",
    ),
) -> Batch:
    """Create a batch and enqueue per-application background processing.

    The response is the batch summary (no embedded applications); poll
    ``GET /batches/{id}`` for progress as background tasks complete.
    """

    # --- meta JSON --------------------------------------------------------
    try:
        meta_payload = json.loads(meta)
    except json.JSONDecodeError as exc:
        raise _http_error(
            code="invalid_meta_json",
            message=f"meta is not valid JSON: {exc.msg}.",
            recovery="Send the meta field as a JSON object string.",
        ) from exc
    try:
        submission = BatchSubmissionMeta.model_validate(meta_payload)
    except ValidationError as exc:
        raise _http_error(
            code="invalid_meta_schema",
            message="meta does not match the required shape.",
            recovery=(
                "Required: importer_name (str), importer_email (str). "
                "Optional: note (str)."
            ),
        ) from exc

    # --- manifest ---------------------------------------------------------
    if manifest.content_type and "csv" not in manifest.content_type and not (
        manifest.filename or ""
    ).lower().endswith(".csv"):
        raise _http_error(
            code="manifest_not_csv",
            message=(
                f"manifest content-type is {manifest.content_type!r}; "
                "expected text/csv."
            ),
            recovery="Upload the manifest as a UTF-8 .csv file.",
        )
    manifest_bytes = await manifest.read()
    if not manifest_bytes:
        raise _http_error(
            code="manifest_empty",
            message="manifest is empty.",
            recovery="Upload a non-empty CSV manifest.",
        )

    parsed = parse_manifest(
        manifest_bytes, max_applications=settings.batch_max_applications
    )
    if not parsed.ok:
        raise _manifest_errors_response(parsed.errors)

    # --- image files (size, type, filename coverage) ----------------------
    by_name: dict[str, UploadFile] = {}
    for upload in images:
        name = upload.filename or ""
        if not name:
            raise _http_error(
                code="image_missing_filename",
                message="One of the uploaded image files has no filename.",
                recovery=(
                    "Ensure every uploaded file has a filename matching "
                    "an image_filename in the manifest."
                ),
            )
        if name in by_name:
            raise _http_error(
                code="duplicate_image_upload",
                message=f"Image filename {name!r} was uploaded twice.",
                recovery="Upload each image file only once.",
            )
        if upload.content_type not in settings.allowed_image_types:
            raise _http_error(
                code="unsupported_image_type",
                message=(
                    f"Image {name!r} has type {upload.content_type!r}; "
                    f"expected PNG or JPEG."
                ),
                recovery="Convert the file to PNG or JPEG and try again.",
                http_status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        by_name[name] = upload

    expected_filenames: set[str] = set()
    for app in parsed.applications:
        expected_filenames.update(app.image_filenames)
    missing = expected_filenames - by_name.keys()
    if missing:
        raise _http_error(
            code="missing_images",
            message=(
                f"Manifest references {len(missing)} image file(s) that "
                f"were not uploaded: {', '.join(sorted(missing))}."
            ),
            recovery="Upload every image referenced by the manifest.",
        )
    extra = by_name.keys() - expected_filenames
    if extra:
        raise _http_error(
            code="extra_images",
            message=(
                f"{len(extra)} uploaded image(s) are not referenced by "
                f"the manifest: {', '.join(sorted(extra))}."
            ),
            recovery=(
                "Either add manifest rows referencing these images, or "
                "remove them from the upload."
            ),
        )

    # --- persist images to disk ------------------------------------------
    # Per-batch subdirectory keeps files for one submission together so
    # operators can inspect or delete in one rm -rf during development.
    submission_dir_id = uuid.uuid4().hex[:12]
    storage_root = Path(settings.batch_storage_dir) / submission_dir_id
    storage_root.mkdir(parents=True, exist_ok=True)

    image_records: dict[str, ImageInput] = {}
    total_bytes = 0
    for filename, upload in by_name.items():
        body = await upload.read()
        if len(body) > settings.max_upload_bytes:
            raise _http_error(
                code="image_too_large",
                message=(
                    f"Image {filename!r} is "
                    f"{len(body) // (1024 * 1024)} MB; the per-file limit "
                    f"is {settings.max_upload_bytes // (1024 * 1024)} MB."
                ),
                recovery="Resize the image and re-upload the batch.",
                http_status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        if not body:
            raise _http_error(
                code="empty_image",
                message=f"Image {filename!r} is zero bytes.",
                recovery="Re-export the image and try again.",
            )
        total_bytes += len(body)
        # Write under a safe basename: strip any path components from
        # the user-provided filename to avoid traversal into other dirs.
        safe_name = Path(filename).name
        target = storage_root / safe_name
        target.write_bytes(body)
        image_records[filename] = ImageInput(
            filename=filename,
            stored_path=str(target),
            attribution=_resolve_attribution(parsed.applications, filename),
            is_primary=_is_primary(parsed.applications, filename),
            byte_size=len(body),
            content_type=upload.content_type or "application/octet-stream",
        )

    # --- create rows in SQLite -------------------------------------------
    application_inputs: list[ApplicationInput] = []
    for app in parsed.applications:
        app_images = tuple(image_records[name] for name in app.image_filenames)
        application_inputs.append(
            ApplicationInput(fields=app.fields, images=app_images)
        )

    store = get_store()
    batch_id = store.create_batch(
        importer_name=submission.importer_name,
        importer_email=submission.importer_email,
        note=submission.note,
        applications=application_inputs,
    )

    # --- queue background processing -------------------------------------
    pending = store.list_pending_application_ids(batch_id)
    schedule_processing(background_tasks, pending)
    logger.info(
        "Created batch %s: %d applications, %d images, %.1f KiB total.",
        batch_id,
        len(application_inputs),
        sum(len(a.images) for a in application_inputs),
        total_bytes / 1024,
    )

    detail = store.get_batch_detail(batch_id)
    if detail is None:
        # Should be unreachable: we just inserted the row.
        raise _http_error(
            code="batch_create_inconsistent",
            message="Batch was created but cannot be read back.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Batch(
        id=detail.id,
        importer_name=detail.importer_name,
        importer_email=detail.importer_email,
        note=detail.note,
        counts=detail.counts,
        created_at=detail.created_at,
    )


def _resolve_attribution(
    apps: tuple[ManifestApplication, ...], filename: str
) -> ImageAttribution:
    """Look up the attribution for an image filename across all apps."""

    for app in apps:
        if filename in app.attributions_by_filename:
            return app.attributions_by_filename[filename]
    # Should be unreachable: caller verifies expected_filenames coverage.
    return ImageAttribution.OTHER


def _is_primary(
    apps: tuple[ManifestApplication, ...], filename: str
) -> bool:
    """True when ``filename`` is the primary image of its application."""

    for app in apps:
        if app.primary_image_filename == filename:
            return True
    return False


# ---------------------------------------------------------------------------
# GET /batches
# ---------------------------------------------------------------------------
@router.get("/batches", response_model=list[Batch])
async def list_batches() -> list[Batch]:
    """All batches, newest first."""

    return get_store().list_batches()


# ---------------------------------------------------------------------------
# GET /batches/{batch_id}
# ---------------------------------------------------------------------------
@router.get(
    "/batches/{batch_id}",
    response_model=BatchDetail,
    responses={404: {"model": AnalyzeError}},
)
async def get_batch(batch_id: str) -> BatchDetail:
    detail = get_store().get_batch_detail(batch_id)
    if detail is None:
        raise _http_error(
            code="batch_not_found",
            message=f"No batch with id {batch_id!r} exists.",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    return detail


# ---------------------------------------------------------------------------
# GET /applications/{id}
# ---------------------------------------------------------------------------
@router.get(
    "/applications/{application_id}",
    response_model=Application,
    responses={404: {"model": AnalyzeError}},
)
async def get_application(application_id: str) -> Application:
    app = get_store().get_application(application_id)
    if app is None:
        raise _http_error(
            code="application_not_found",
            message=f"No application with id {application_id!r} exists.",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    return app


# ---------------------------------------------------------------------------
# GET /applications/{id}/images/{image_id}
# ---------------------------------------------------------------------------
@router.get(
    "/applications/{application_id}/images/{image_id}",
    responses={404: {"model": AnalyzeError}},
)
async def get_application_image(
    application_id: str, image_id: str
) -> FileResponse:
    """Serve the on-disk bytes for one label image.

    Both ``application_id`` and ``image_id`` must match a single row in
    ``label_images``; that pairing prevents callers from using one
    application's id to read another's image. Returns 404 if either id
    is unknown or if the on-disk file has been removed.
    """

    record = get_store().get_image_for_application(application_id, image_id)
    if record is None:
        raise _http_error(
            code="image_not_found",
            message=(
                f"No image with id {image_id!r} exists for application "
                f"{application_id!r}."
            ),
            http_status=status.HTTP_404_NOT_FOUND,
        )
    stored_path, content_type, filename = record
    path = Path(stored_path)
    if not path.is_file():
        # The DB row points to a missing file. Treat as 404 so the UI
        # falls back gracefully instead of returning a 500.
        logger.warning(
            "Image %s for application %s is missing on disk at %s",
            image_id,
            application_id,
            stored_path,
        )
        raise _http_error(
            code="image_not_found",
            message="The image file is no longer available on disk.",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    return FileResponse(
        str(path),
        media_type=content_type or "application/octet-stream",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# PUT /applications/{id}/decision
# ---------------------------------------------------------------------------
@router.put(
    "/applications/{application_id}/decision",
    response_model=Application,
    responses={404: {"model": AnalyzeError}},
)
async def set_decision(
    application_id: str, decision: WorkflowDecision
) -> Application:
    """Set the analyst's workflow status. Idempotent — overwrites previous."""

    store = get_store()
    if not store.set_workflow_status(
        application_id, decision.workflow_status, decision.note
    ):
        raise _http_error(
            code="application_not_found",
            message=f"No application with id {application_id!r} exists.",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    app = store.get_application(application_id)
    if app is None:  # extremely unlikely race; treat as 404
        raise _http_error(
            code="application_not_found",
            message=f"No application with id {application_id!r} exists.",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    return app


# ---------------------------------------------------------------------------
# POST /batches/{id}/bulk-approve
# ---------------------------------------------------------------------------
@router.post(
    "/batches/{batch_id}/bulk-approve",
    response_model=BulkApproveResponse,
    responses={404: {"model": AnalyzeError}},
)
async def bulk_approve(batch_id: str) -> BulkApproveResponse:
    """Approve every PENDING_REVIEW application that meets the eligibility
    rule (every comparison Match, every confidence high). Returns counts
    so the UI can display a confirmation toast.
    """

    store = get_store()
    detail = store.get_batch_detail(batch_id)
    if detail is None:
        raise _http_error(
            code="batch_not_found",
            message=f"No batch with id {batch_id!r} exists.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    eligible: list[str] = []
    skipped_reasons: dict[str, int] = {
        "still_processing": 0,
        "already_decided": 0,
        "failed": 0,
        "needs_review": 0,
    }
    for app in detail.applications:
        if app.processing_status in (
            ApplicationProcessingStatus.PROCESSING,
            ApplicationProcessingStatus.PENDING,
        ):
            skipped_reasons["still_processing"] += 1
            continue
        if app.processing_status == ApplicationProcessingStatus.FAILED:
            skipped_reasons["failed"] += 1
            continue
        if app.workflow_status != WorkflowStatus.PENDING_REVIEW:
            skipped_reasons["already_decided"] += 1
            continue
        if is_eligible_for_bulk_approve(app):
            eligible.append(app.id)
        else:
            skipped_reasons["needs_review"] += 1

    approved = store.bulk_approve_eligible(batch_id, eligible_app_ids=eligible)
    skipped = sum(skipped_reasons.values()) + (len(eligible) - approved)
    return BulkApproveResponse(
        approved_count=approved,
        skipped_count=skipped,
        skipped_reasons={k: v for k, v in skipped_reasons.items() if v > 0},
    )
