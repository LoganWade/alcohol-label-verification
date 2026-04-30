"""Background processor: runs the existing analyze() pipeline on each
application's primary image, persists the result via BatchStore.

This module is the only place the batch flow touches the existing
single-image pipeline. Reusing ``analyze()`` verbatim — instead of
forking a batch-specific variant — keeps a single pipeline definition
and means PR review feedback on the OCR/comparison stages benefits both
flows automatically.

Entry points
------------
- ``process_application(app_id)`` — synchronous; one application end to end.
- ``schedule_processing(background_tasks, app_ids)`` — called by the
  POST /batches handler; queues one task per pending application.

Why FastAPI ``BackgroundTasks`` instead of Celery: see
docs/tradeoffs.md "Background processing without Celery". One uvicorn
worker, no Redis, prototype scope.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import BackgroundTasks

from app.schemas.fields import ExpectedFields
from app.schemas.review import AnalyzeError
from app.services.batch.storage import BatchStore, get_store
from app.services.pipeline import analyze

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-application processing (sync entrypoint)
# ---------------------------------------------------------------------------
def process_application(app_id: str, store: BatchStore | None = None) -> None:
    """Run the pipeline for one application and persist the result.

    Always returns None and never raises: any failure is mapped to a
    persisted ``AnalyzeError`` envelope on the application row, mirroring
    the contract of the single-image /analyze endpoint. The frontend
    renders the same error shape across both flows.

    The analyze pipeline is fully synchronous (OpenCV preprocess +
    PaddleOCR is CPU-bound) and we are already on a worker thread when
    BackgroundTasks dispatches us, so we call it directly. The PaddleOCR
    threading-safety lock in ``services/extraction/ocr/paddle_ocr.py``
    keeps concurrent applications from corrupting the shared instance.
    """

    s = store or get_store()
    fields = s.get_application_fields(app_id)
    if fields is None:
        logger.warning("process_application: app_id %s not found", app_id)
        return

    primary_path = s.get_primary_image_path(app_id)
    if primary_path is None:
        s.set_failed(
            app_id,
            AnalyzeError(
                code="missing_primary_image",
                message=(
                    "This application has no primary image to analyze. "
                    "Re-upload the batch with a primary image marked."
                ),
            ),
        )
        return

    s.set_processing(app_id)

    try:
        image_bytes = Path(primary_path).read_bytes()
    except OSError as exc:
        logger.exception("process_application: cannot read %s", primary_path)
        s.set_failed(
            app_id,
            AnalyzeError(
                code="image_unreadable_on_disk",
                message=(
                    f"Could not read the primary image file: {exc.strerror or exc!s}."
                ),
                recovery_hint=(
                    "Re-upload the batch. The image may have been removed "
                    "from temporary storage."
                ),
            ),
        )
        return

    if not image_bytes:
        s.set_failed(
            app_id,
            AnalyzeError(
                code="empty_image",
                message="The primary image is zero bytes.",
                recovery_hint="Re-upload the batch with a valid image file.",
            ),
        )
        return

    expected = ExpectedFields(
        brand_name=fields.brand_name,
        class_type=fields.class_type,
        alcohol_content=fields.alcohol_content,
        net_contents=fields.net_contents,
        bottler=fields.bottler,
        country_of_origin=fields.country_of_origin,
        warning=None,  # default to statutory text
    )

    try:
        response = analyze(image_bytes, expected)
    except ValueError as exc:
        # Mirrors /analyze's "unreadable_image" 422 response shape.
        s.set_failed(
            app_id,
            AnalyzeError(
                code="unreadable_image",
                message=(
                    "The image could not be read. "
                    "It may be corrupt or in an unsupported format."
                ),
                recovery_hint=(
                    "Re-save the image as PNG or JPEG and re-upload the batch."
                ),
            ),
        )
        logger.exception("process_application(%s): unreadable image: %s", app_id, exc)
        return
    except Exception as exc:
        # Pipeline failures are operator-visible (logs + persisted error).
        # We don't want one bad image to crash the worker thread.
        s.set_failed(
            app_id,
            AnalyzeError(
                code="pipeline_error",
                message=f"The analysis pipeline failed: {exc!s}",
                recovery_hint=(
                    "Re-upload the batch. If the error persists for the "
                    "same image, the file may be unsupported."
                ),
            ),
        )
        logger.exception("process_application(%s): pipeline failure", app_id)
        return

    s.set_done(app_id, response)


# ---------------------------------------------------------------------------
# Async wrapper for BackgroundTasks
# ---------------------------------------------------------------------------
async def _process_application_async(app_id: str) -> None:
    """Run process_application on a worker thread.

    BackgroundTasks awaits coroutines on the event loop; we offload the
    CPU-heavy pipeline to ``asyncio.to_thread`` so other requests stay
    responsive on the single uvicorn worker. Same pattern as the
    /analyze handler.
    """

    await asyncio.to_thread(process_application, app_id)


def schedule_processing(
    background_tasks: BackgroundTasks, app_ids: list[str]
) -> None:
    """Queue one background task per application id.

    Tasks run sequentially in the order added (FastAPI's BackgroundTasks
    awaits each one). PaddleOCR's ``.ocr()`` is serialized inside the
    provider, so even if FastAPI later changes to parallel dispatch the
    OCR step stays safe.
    """

    for app_id in app_ids:
        background_tasks.add_task(_process_application_async, app_id)


__all__ = ["process_application", "schedule_processing"]
