"""Tests for the background processor.

The processor is the bridge between the batch tables and the existing
analyze() pipeline. We assert it (a) reads the primary image, (b)
persists a successful response on the application row, (c) maps
filesystem and pipeline errors to AnalyzeError envelopes without
raising, and (d) is a no-op for unknown application ids.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.constants import (
    ApplicationProcessingStatus,
    ImageAttribution,
)
from app.schemas.batch import ApplicationFields
from app.services.batch.processor import process_application
from app.services.batch.storage import (
    ApplicationInput,
    BatchStore,
    ImageInput,
)


def _real_png(path: Path) -> int:
    img = Image.new("RGB", (64, 64), color="white")
    img.save(path, format="PNG")
    return path.stat().st_size


@pytest.fixture()
def store(tmp_path: Path) -> BatchStore:
    s = BatchStore(tmp_path / "p.db")
    s.apply_migrations()
    return s


def test_process_application_runs_pipeline_and_marks_done(
    store: BatchStore, tmp_path: Path
) -> None:
    img_path = tmp_path / "a.png"
    size = _real_png(img_path)

    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[
            ApplicationInput(
                fields=ApplicationFields(serial_number="A1", brand_name="X"),
                images=(
                    ImageInput(
                        filename="a.png",
                        stored_path=str(img_path),
                        attribution=ImageAttribution.FRONT,
                        is_primary=True,
                        byte_size=size,
                        content_type="image/png",
                    ),
                ),
            )
        ],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]

    process_application(app_id, store=store)

    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.DONE
    assert app.analyze is not None
    assert app.error is None


def test_process_application_handles_missing_image_file(
    store: BatchStore, tmp_path: Path
) -> None:
    # File path points at a non-existent file
    nonexistent = tmp_path / "ghost.png"
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[
            ApplicationInput(
                fields=ApplicationFields(serial_number="A1"),
                images=(
                    ImageInput(
                        filename="ghost.png",
                        stored_path=str(nonexistent),
                        attribution=ImageAttribution.FRONT,
                        is_primary=True,
                        byte_size=0,
                        content_type="image/png",
                    ),
                ),
            )
        ],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]

    # Must not raise.
    process_application(app_id, store=store)

    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.FAILED
    assert app.error is not None
    assert app.error.code == "image_unreadable_on_disk"


def test_process_application_handles_unknown_id(store: BatchStore) -> None:
    # No row, no exception, no DB writes.
    process_application("app_does_not_exist", store=store)


def test_process_application_handles_zero_byte_image(
    store: BatchStore, tmp_path: Path
) -> None:
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")

    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[
            ApplicationInput(
                fields=ApplicationFields(serial_number="A1"),
                images=(
                    ImageInput(
                        filename="empty.png",
                        stored_path=str(empty),
                        attribution=ImageAttribution.FRONT,
                        is_primary=True,
                        byte_size=0,
                        content_type="image/png",
                    ),
                ),
            )
        ],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    process_application(app_id, store=store)

    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.FAILED
    assert app.error is not None
    assert app.error.code == "empty_image"


# Quiet ruff about unused import
_ = io
