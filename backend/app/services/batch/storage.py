"""SQLite-backed persistence for the batch-upload feature.

All ``sqlite3`` I/O is funneled through ``BatchStore`` so the rest of the
codebase never opens a connection or builds a SQL string. The store is
intentionally small: ten methods covering the lifecycle of a batch, an
application, and a label image. Anything more elaborate (joins,
aggregations) is composed in Python from these primitives.

Design choices
--------------
- One short-lived connection per call (``_connect`` context manager). SQLite
  serializes writes anyway and the prototype has at most one uvicorn worker
  on HF Spaces, so connection pooling buys nothing here.
- ``check_same_thread=False`` because FastAPI's threadpool may run the
  handler on a different thread than the background task. SQLite is
  thread-safe with the default *serialized* threading mode; we still avoid
  sharing a single connection across threads by opening one per call.
- ``foreign_keys = ON`` and ``journal_mode = WAL`` set on every connection.
  WAL gives readers non-blocking access while a writer is active, which is
  what GET endpoints want while a background task is mid-write.
- All datetimes stored as ISO-8601 strings via ``datetime('now')`` in the
  schema and ``_utc_now_iso()`` from Python. SQLite has no native datetime
  type and we avoid adapter/converter magic.

Concurrency
-----------
SQLite handles "many readers, one writer" with WAL. The background
processor writes to one application row at a time; the API reads. Bulk
approve and the analyst's PUT are short transactions. We do not need
explicit locking.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.constants import (
    BULK_APPROVE_REQUIRES_CONFIDENCE,
    ApplicationProcessingStatus,
    FieldStatus,
    ImageAttribution,
    WorkflowStatus,
)
from app.schemas.batch import (
    Application,
    ApplicationFields,
    Batch,
    BatchDetail,
    BatchSummaryCounts,
    LabelImage,
)
from app.schemas.review import AnalyzeError, AnalyzeResponse
from app.services.batch import migrations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string with second precision.

    Matches the format SQLite's ``datetime('now')`` produces so timestamps
    written from Python and from SQL sort lexicographically together.
    """

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _new_id(prefix: str) -> str:
    """Short, prefixed, URL-safe identifier.

    Uses the first 12 chars of a UUID4 hex (~48 bits of entropy) — plenty
    for a prototype with at most a few thousand rows, and far easier to
    eyeball in the URL bar than a full UUID. Collisions are guarded by the
    PRIMARY KEY constraint, which would surface as an ``IntegrityError``.
    """

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Image input record (used by create_batch)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ImageInput:
    """One image to attach to an application during batch creation.

    Decoupled from ``LabelImage`` (the API response shape) so the caller
    can pass a freshly-stored file's path + metadata without first
    materializing an ID.
    """

    filename: str
    stored_path: str
    attribution: ImageAttribution
    is_primary: bool
    byte_size: int
    content_type: str


@dataclass(frozen=True, slots=True)
class ApplicationInput:
    """One application's worth of input passed to ``create_batch``.

    The store assigns ``id`` for the application and for each image; the
    caller supplies the importer-stated fields and the already-persisted
    images.
    """

    fields: ApplicationFields
    images: tuple[ImageInput, ...]


# ---------------------------------------------------------------------------
# BatchStore
# ---------------------------------------------------------------------------
class BatchStore:
    """Thin wrapper over ``sqlite3`` for the batch tables.

    Construct once at app startup with ``BatchStore(db_path)``. All methods
    are safe to call from request handlers and from background tasks; each
    opens its own connection.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        # Ensure the parent directory exists so the first connection does
        # not fail with ENOENT. The DB file itself is created on demand by
        # sqlite3 on first connect.
        parent = Path(self._db_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    # -- internals ----------------------------------------------------------
    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions explicitly
            timeout=5.0,
        )
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
        finally:
            conn.close()

    def apply_migrations(self) -> None:
        """Run any pending schema migrations. Idempotent; safe on every startup."""

        with self._connect() as conn:
            migrations.apply(conn)

    # -- create -------------------------------------------------------------
    def create_batch(
        self,
        *,
        importer_name: str,
        importer_email: str,
        note: str | None,
        applications: list[ApplicationInput],
    ) -> str:
        """Insert one batch and all its applications + images atomically.

        Returns the new batch_id. Raises ``sqlite3.IntegrityError`` if any
        ``(batch_id, serial_number)`` pair is duplicated within the batch
        (the manifest parser is expected to catch this earlier with a
        better error, but the DB is the final guard).
        """

        batch_id = _new_id("bat")
        now = _utc_now_iso()
        with self._connect() as conn:
            with conn:  # transaction
                conn.execute(
                    """
                    INSERT INTO batches (id, importer_name, importer_email, note, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (batch_id, importer_name, importer_email, note, now),
                )
                for app in applications:
                    app_id = _new_id("app")
                    f = app.fields
                    conn.execute(
                        """
                        INSERT INTO applications (
                            id, batch_id,
                            serial_number, brand_name, fanciful_name, class_type,
                            alcohol_content, net_contents, bottler, country_of_origin,
                            processing_status, workflow_status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            app_id,
                            batch_id,
                            f.serial_number,
                            f.brand_name,
                            f.fanciful_name,
                            f.class_type,
                            f.alcohol_content,
                            f.net_contents,
                            f.bottler,
                            f.country_of_origin,
                            ApplicationProcessingStatus.PENDING.value,
                            WorkflowStatus.PENDING_REVIEW.value,
                            now,
                        ),
                    )
                    for img in app.images:
                        img_id = _new_id("img")
                        conn.execute(
                            """
                            INSERT INTO label_images (
                                id, application_id, filename, stored_path,
                                attribution, is_primary, byte_size, content_type,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                img_id,
                                app_id,
                                img.filename,
                                img.stored_path,
                                img.attribution.value,
                                1 if img.is_primary else 0,
                                img.byte_size,
                                img.content_type,
                                now,
                            ),
                        )
        return batch_id

    # -- background-processor mutations ------------------------------------
    def list_pending_application_ids(self, batch_id: str) -> list[str]:
        """Return application ids in PENDING state for the given batch.

        Used by the API right after batch creation to enqueue background
        processing tasks.
        """

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id FROM applications
                WHERE batch_id = ? AND processing_status = ?
                ORDER BY created_at ASC, id ASC
                """,
                (batch_id, ApplicationProcessingStatus.PENDING.value),
            )
            return [row["id"] for row in cur.fetchall()]

    def get_primary_image_path(self, application_id: str) -> str | None:
        """Return the on-disk path of the primary image for an application,
        or ``None`` if the application has no primary image (which the
        manifest parser should prevent)."""

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT stored_path FROM label_images
                WHERE application_id = ? AND is_primary = 1
                ORDER BY created_at ASC LIMIT 1
                """,
                (application_id,),
            )
            row = cur.fetchone()
            return row["stored_path"] if row else None

    def get_image_for_application(
        self, application_id: str, image_id: str
    ) -> tuple[str, str, str] | None:
        """Return ``(stored_path, content_type, filename)`` for one image
        belonging to the given application, or ``None`` if there is no row
        matching both IDs.

        Both IDs are required (and must match) so callers cannot use one
        application's id to fetch another application's image.
        """

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT stored_path, content_type, filename FROM label_images
                WHERE id = ? AND application_id = ?
                """,
                (image_id, application_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return (
                row["stored_path"],
                row["content_type"],
                row["filename"],
            )

    def get_application_fields(self, application_id: str) -> ApplicationFields | None:
        """Return the importer-stated fields for one application."""

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT serial_number, brand_name, fanciful_name, class_type,
                       alcohol_content, net_contents, bottler, country_of_origin
                FROM applications WHERE id = ?
                """,
                (application_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return ApplicationFields(**dict(row))

    def set_processing(self, application_id: str) -> None:
        """Transition application to PROCESSING. No-op if already past it."""

        with self._connect() as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE applications
                    SET processing_status = ?
                    WHERE id = ? AND processing_status = ?
                    """,
                    (
                        ApplicationProcessingStatus.PROCESSING.value,
                        application_id,
                        ApplicationProcessingStatus.PENDING.value,
                    ),
                )

    def set_done(self, application_id: str, response: AnalyzeResponse) -> None:
        """Persist a successful analyze response and mark DONE."""

        payload = response.model_dump_json()
        now = _utc_now_iso()
        with self._connect() as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE applications
                    SET processing_status = ?,
                        analyze_response_json = ?,
                        error_code = NULL,
                        error_message = NULL,
                        processed_at = ?
                    WHERE id = ?
                    """,
                    (
                        ApplicationProcessingStatus.DONE.value,
                        payload,
                        now,
                        application_id,
                    ),
                )

    def set_failed(self, application_id: str, error: AnalyzeError) -> None:
        """Persist a pipeline failure and mark FAILED.

        ``error`` is the same AnalyzeError envelope the /analyze endpoint
        returns, so the frontend renders a single error shape across the
        single-image and batch flows.
        """

        now = _utc_now_iso()
        with self._connect() as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE applications
                    SET processing_status = ?,
                        error_code = ?,
                        error_message = ?,
                        processed_at = ?
                    WHERE id = ?
                    """,
                    (
                        ApplicationProcessingStatus.FAILED.value,
                        error.code,
                        error.message,
                        now,
                        application_id,
                    ),
                )

    # -- workflow status (analyst decisions) -------------------------------
    def set_workflow_status(
        self,
        application_id: str,
        status: WorkflowStatus,
        note: str | None = None,
    ) -> bool:
        """Set the analyst's decision on an application.

        Returns True if the row was updated, False if no application with
        the given id exists. Always overwrites the previous decision —
        analysts can flip a status as many times as they need; we keep
        only the latest. (See tradeoffs.md "Workflow status vocabulary".)
        """

        now = _utc_now_iso()
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE applications
                    SET workflow_status = ?,
                        decided_note = ?,
                        decided_at = ?
                    WHERE id = ?
                    """,
                    (status.value, note, now, application_id),
                )
                return cur.rowcount > 0

    # -- reads --------------------------------------------------------------
    def list_batches(self) -> list[Batch]:
        """Return all batches with summary counts, newest first."""

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT b.id, b.importer_name, b.importer_email, b.note, b.created_at
                FROM batches b
                ORDER BY b.created_at DESC, b.id DESC
                """
            )
            rows = cur.fetchall()
            results: list[Batch] = []
            for row in rows:
                counts = self._counts_for_batch(conn, row["id"])
                results.append(
                    Batch(
                        id=row["id"],
                        importer_name=row["importer_name"],
                        importer_email=row["importer_email"],
                        note=row["note"],
                        counts=counts,
                        created_at=row["created_at"],
                    )
                )
            return results

    def get_batch_detail(self, batch_id: str) -> BatchDetail | None:
        """Return one batch with embedded applications + images.

        Issues three queries: batches header, applications, images. We
        fan out images by application_id in Python rather than a SQL JOIN
        because the row count is small (<=100 apps, a few images each)
        and assembling Pydantic models from a flat join row by row is
        more error-prone.
        """

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, importer_name, importer_email, note, created_at
                FROM batches WHERE id = ?
                """,
                (batch_id,),
            )
            header = cur.fetchone()
            if header is None:
                return None

            counts = self._counts_for_batch(conn, batch_id)
            applications = self._applications_for_batch(conn, batch_id)
            return BatchDetail(
                id=header["id"],
                importer_name=header["importer_name"],
                importer_email=header["importer_email"],
                note=header["note"],
                counts=counts,
                created_at=header["created_at"],
                applications=applications,
            )

    def get_application(self, application_id: str) -> Application | None:
        """Return one application with embedded images (no batch context)."""

        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM applications WHERE id = ?
                """,
                (application_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            images = self._images_for_application(conn, application_id)
            return _row_to_application(row, images)

    # -- bulk approve ------------------------------------------------------
    def bulk_approve_eligible(
        self,
        batch_id: str,
        *,
        eligible_app_ids: list[str],
    ) -> int:
        """Set workflow_status = APPROVED for the given app ids in one tx.

        Eligibility (every comparison is Match + every confidence is HIGH)
        is computed by the API layer from ``analyze_response_json`` —
        keeping the SQL trivial and the eligibility rule inspectable in
        Python, where the comparison vocabulary already lives.

        Returns the number of rows actually updated. Applications that
        already have a non-PENDING_REVIEW workflow_status are skipped so
        we never silently overturn a prior analyst decision.
        """

        if not eligible_app_ids:
            return 0
        now = _utc_now_iso()
        placeholders = ",".join("?" * len(eligible_app_ids))
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    f"""
                    UPDATE applications
                    SET workflow_status = ?,
                        decided_at = ?,
                        decided_note = ?
                    WHERE batch_id = ?
                      AND workflow_status = ?
                      AND id IN ({placeholders})
                    """,
                    (
                        WorkflowStatus.APPROVED.value,
                        now,
                        "Bulk-approved (all fields Match, all confidences high).",
                        batch_id,
                        WorkflowStatus.PENDING_REVIEW.value,
                        *eligible_app_ids,
                    ),
                )
                return cur.rowcount

    # -- internal assembly --------------------------------------------------
    def _counts_for_batch(
        self, conn: sqlite3.Connection, batch_id: str
    ) -> BatchSummaryCounts:
        cur = conn.execute(
            """
            SELECT processing_status, workflow_status, COUNT(*) AS n
            FROM applications WHERE batch_id = ?
            GROUP BY processing_status, workflow_status
            """,
            (batch_id,),
        )
        totals: dict[str, int] = {}
        total = 0
        for row in cur.fetchall():
            n = int(row["n"])
            total += n
            totals[f"p:{row['processing_status']}"] = (
                totals.get(f"p:{row['processing_status']}", 0) + n
            )
            totals[f"w:{row['workflow_status']}"] = (
                totals.get(f"w:{row['workflow_status']}", 0) + n
            )
        return BatchSummaryCounts(
            total=total,
            pending=totals.get(f"p:{ApplicationProcessingStatus.PENDING.value}", 0),
            processing=totals.get(
                f"p:{ApplicationProcessingStatus.PROCESSING.value}", 0
            ),
            done=totals.get(f"p:{ApplicationProcessingStatus.DONE.value}", 0),
            failed=totals.get(f"p:{ApplicationProcessingStatus.FAILED.value}", 0),
            approved=totals.get(f"w:{WorkflowStatus.APPROVED.value}", 0),
            rejected=totals.get(f"w:{WorkflowStatus.REJECTED.value}", 0),
            needs_correction=totals.get(
                f"w:{WorkflowStatus.NEEDS_CORRECTION.value}", 0
            ),
        )

    def _applications_for_batch(
        self, conn: sqlite3.Connection, batch_id: str
    ) -> list[Application]:
        cur = conn.execute(
            """
            SELECT * FROM applications
            WHERE batch_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (batch_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return []
        # Single image fetch for all apps in this batch; group in Python.
        app_ids = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(app_ids))
        cur = conn.execute(
            f"""
            SELECT * FROM label_images
            WHERE application_id IN ({placeholders})
            ORDER BY is_primary DESC, created_at ASC, id ASC
            """,
            tuple(app_ids),
        )
        images_by_app: dict[str, list[LabelImage]] = {}
        for img_row in cur.fetchall():
            images_by_app.setdefault(img_row["application_id"], []).append(
                _row_to_label_image(img_row)
            )
        return [
            _row_to_application(row, images_by_app.get(row["id"], []))
            for row in rows
        ]

    def _images_for_application(
        self, conn: sqlite3.Connection, application_id: str
    ) -> list[LabelImage]:
        cur = conn.execute(
            """
            SELECT * FROM label_images
            WHERE application_id = ?
            ORDER BY is_primary DESC, created_at ASC, id ASC
            """,
            (application_id,),
        )
        return [_row_to_label_image(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Row -> Pydantic adapters (module-level so tests can call them too)
# ---------------------------------------------------------------------------
def _row_to_label_image(row: sqlite3.Row) -> LabelImage:
    return LabelImage(
        id=row["id"],
        filename=row["filename"],
        attribution=ImageAttribution(row["attribution"]),
        is_primary=bool(row["is_primary"]),
        byte_size=int(row["byte_size"]),
        content_type=row["content_type"],
    )


def _row_to_application(
    row: sqlite3.Row, images: list[LabelImage]
) -> Application:
    fields = ApplicationFields(
        serial_number=row["serial_number"],
        brand_name=row["brand_name"],
        fanciful_name=row["fanciful_name"],
        class_type=row["class_type"],
        alcohol_content=row["alcohol_content"],
        net_contents=row["net_contents"],
        bottler=row["bottler"],
        country_of_origin=row["country_of_origin"],
    )

    analyze: AnalyzeResponse | None = None
    payload = row["analyze_response_json"]
    if payload:
        # ``model_validate_json`` would re-validate; we trust what we wrote
        # to the DB but still parse defensively to fail loud on schema drift.
        try:
            analyze = AnalyzeResponse.model_validate(json.loads(payload))
        except Exception:
            analyze = None

    error: AnalyzeError | None = None
    if row["error_code"]:
        error = AnalyzeError(
            code=row["error_code"],
            message=row["error_message"] or "",
        )

    return Application(
        id=row["id"],
        batch_id=row["batch_id"],
        fields=fields,
        processing_status=ApplicationProcessingStatus(row["processing_status"]),
        workflow_status=WorkflowStatus(row["workflow_status"]),
        images=images,
        analyze=analyze,
        error=error,
        created_at=row["created_at"],
        processed_at=row["processed_at"],
        decided_at=row["decided_at"],
        decided_note=row["decided_note"],
    )


# ---------------------------------------------------------------------------
# Eligibility for bulk-approve (lives here because it operates over the
# same row payload the store reads back)
# ---------------------------------------------------------------------------
def is_eligible_for_bulk_approve(application: Application) -> bool:
    """True when every comparison is Match AND every confidence is HIGH.

    Conservative by design: any Mismatch / Missing / Needs Review / Uncertain
    or any non-HIGH confidence (including the warning validator) blocks
    auto-approval. The analyst still has to look. See tradeoffs.md
    "Bulk-approve clean matches".
    """

    if application.processing_status != ApplicationProcessingStatus.DONE:
        return False
    if application.workflow_status != WorkflowStatus.PENDING_REVIEW:
        return False
    if application.analyze is None:
        return False

    a = application.analyze
    if a.warning_validation.status != FieldStatus.MATCH:
        return False
    for cmp in a.field_comparisons:
        if cmp.status != FieldStatus.MATCH:
            return False
        if cmp.confidence not in BULK_APPROVE_REQUIRES_CONFIDENCE:
            return False
    return True


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_store_singleton: BatchStore | None = None


def get_store() -> BatchStore:
    """Return the process-wide BatchStore, constructing it on first call."""

    global _store_singleton
    if _store_singleton is None:
        from app.core.settings import settings  # avoid import cycle at module load

        _store_singleton = BatchStore(settings.batch_db_path)
        _store_singleton.apply_migrations()
    return _store_singleton


def reset_store_for_tests(db_path: str | Path) -> BatchStore:
    """Replace the singleton with a fresh store at ``db_path``. Test-only.

    The migrations runner is invoked so the new file is ready to use.
    """

    global _store_singleton
    _store_singleton = BatchStore(db_path)
    _store_singleton.apply_migrations()
    return _store_singleton


__all__ = [
    "ApplicationInput",
    "BatchStore",
    "ImageInput",
    "get_store",
    "is_eligible_for_bulk_approve",
    "reset_store_for_tests",
]


