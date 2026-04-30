"""Tests for the SQLite-backed BatchStore.

These exercise the full lifecycle of a batch: create, read back, mark
processing/done/failed, set workflow status, bulk approve. The store is
the only path between the API and SQLite, so coverage here is the main
guarantee that schema and Pydantic adapters stay in sync.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.constants import (
    ApplicationProcessingStatus,
    Confidence,
    FieldStatus,
    ImageAttribution,
    ReviewStatus,
    WorkflowStatus,
)
from app.schemas.batch import ApplicationFields
from app.schemas.fields import (
    ExtractedField,
    ExtractedFields,
    FieldName,
)
from app.schemas.pipeline import StageTimings
from app.schemas.review import (
    AnalyzeError,
    AnalyzeResponse,
    FieldComparison,
    ProcessingMetadata,
    ReviewSummary,
    WarningValidation,
)
from app.services.batch.storage import (
    ApplicationInput,
    BatchStore,
    ImageInput,
    is_eligible_for_bulk_approve,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path: Path) -> BatchStore:
    s = BatchStore(tmp_path / "alv.db")
    s.apply_migrations()
    return s


def _img(name: str, *, primary: bool = True) -> ImageInput:
    return ImageInput(
        filename=name,
        stored_path=f"/tmp/{name}",
        attribution=ImageAttribution.FRONT if primary else ImageAttribution.BACK,
        is_primary=primary,
        byte_size=128,
        content_type="image/png",
    )


def _app(serial: str, *, brand: str | None = "Brand X") -> ApplicationInput:
    return ApplicationInput(
        fields=ApplicationFields(serial_number=serial, brand_name=brand),
        images=(_img(f"{serial}.png"),),
    )


def _make_clean_response(
    *, all_high: bool = True, all_match: bool = True
) -> AnalyzeResponse:
    """Build a synthetic AnalyzeResponse that is bulk-approve eligible
    by default, or not — used to exercise eligibility logic."""

    confidence = Confidence.HIGH if all_high else Confidence.MEDIUM
    field_status = FieldStatus.MATCH if all_match else FieldStatus.MISMATCH
    extracted = ExtractedFields(
        brand_name=ExtractedField(field=FieldName.BRAND_NAME, confidence=confidence),
        class_type=ExtractedField(field=FieldName.CLASS_TYPE, confidence=confidence),
        alcohol_content=ExtractedField(
            field=FieldName.ALCOHOL_CONTENT, confidence=confidence
        ),
        net_contents=ExtractedField(
            field=FieldName.NET_CONTENTS, confidence=confidence
        ),
        bottler=ExtractedField(field=FieldName.BOTTLER, confidence=confidence),
        country_of_origin=ExtractedField(
            field=FieldName.COUNTRY_OF_ORIGIN, confidence=confidence
        ),
        warning=ExtractedField(field=FieldName.WARNING, confidence=confidence),
    )
    comparisons = [
        FieldComparison(
            field=fn,
            expected="x",
            found_raw="x",
            found_normalized="x",
            status=field_status,
            reason="ok",
            confidence=confidence,
        )
        for fn in (
            FieldName.BRAND_NAME,
            FieldName.CLASS_TYPE,
            FieldName.ALCOHOL_CONTENT,
            FieldName.NET_CONTENTS,
            FieldName.BOTTLER,
            FieldName.COUNTRY_OF_ORIGIN,
        )
    ]
    return AnalyzeResponse(
        review_id="rev_test",
        summary=ReviewSummary(status=ReviewStatus.PASS, headline="ok"),
        extracted_fields=extracted,
        field_comparisons=comparisons,
        warning_validation=WarningValidation(
            status=field_status,
            header_caps_ok=True,
            wording_match=all_match,
            raw_text="GOVERNMENT WARNING",
            expected_text="GOVERNMENT WARNING",
            reason="ok",
        ),
        processing=ProcessingMetadata(
            elapsed_ms=100,
            image_quality="good",  # type: ignore[arg-type]
            stages_ms=StageTimings(),
            ocr_provider="stub",
            version="0.1.0",
        ),
    )


# ---------------------------------------------------------------------------
# create_batch + read-back
# ---------------------------------------------------------------------------
def test_create_batch_round_trip(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme Imports",
        importer_email="ops@acme.com",
        note="hello",
        applications=[_app("A1"), _app("A2")],
    )
    assert batch_id.startswith("bat_")

    detail = store.get_batch_detail(batch_id)
    assert detail is not None
    assert detail.importer_name == "Acme Imports"
    assert detail.importer_email == "ops@acme.com"
    assert detail.note == "hello"
    assert detail.counts.total == 2
    assert detail.counts.pending == 2
    assert {a.fields.serial_number for a in detail.applications} == {"A1", "A2"}
    for app in detail.applications:
        assert app.processing_status == ApplicationProcessingStatus.PENDING
        assert app.workflow_status == WorkflowStatus.PENDING_REVIEW
        assert len(app.images) == 1
        assert app.images[0].is_primary is True


def test_duplicate_serial_within_batch_raises(store: BatchStore) -> None:
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store.create_batch(
            importer_name="Acme",
            importer_email="ops@acme.com",
            note=None,
            applications=[_app("A1"), _app("A1")],
        )


def test_list_batches_returns_all_with_summary(store: BatchStore) -> None:
    # Two batches at the same wall-clock second often end up identically
    # timestamped (we record only second precision). The store's tiebreaker
    # is id ASC, which is unpredictable for random UUIDs - so this test
    # asserts set membership and the per-batch summary, not the relative
    # order. Order across distinct seconds is covered implicitly by
    # `created_at DESC` in the SQL.
    b1 = store.create_batch(
        importer_name="One",
        importer_email="one@example.com",
        note=None,
        applications=[_app("S1")],
    )
    b2 = store.create_batch(
        importer_name="Two",
        importer_email="two@example.com",
        note=None,
        applications=[_app("S1"), _app("S2")],
    )
    listed = store.list_batches()
    by_id = {b.id: b for b in listed}
    assert {b1, b2} <= by_id.keys()
    assert by_id[b1].counts.total == 1
    assert by_id[b2].counts.total == 2


def test_get_batch_returns_none_for_unknown(store: BatchStore) -> None:
    assert store.get_batch_detail("bat_does_not_exist") is None


# ---------------------------------------------------------------------------
# Processing-state transitions
# ---------------------------------------------------------------------------
def test_processing_lifecycle_pending_processing_done(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    pending = store.list_pending_application_ids(batch_id)
    assert len(pending) == 1
    app_id = pending[0]

    store.set_processing(app_id)
    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.PROCESSING

    store.set_done(app_id, _make_clean_response())
    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.DONE
    assert app.analyze is not None
    assert app.analyze.summary.status == ReviewStatus.PASS
    assert app.processed_at is not None

    # No longer pending
    assert store.list_pending_application_ids(batch_id) == []


def test_set_processing_is_no_op_when_not_pending(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    store.set_done(app_id, _make_clean_response())
    # Calling set_processing now must NOT regress the row.
    store.set_processing(app_id)
    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.DONE


def test_set_failed_persists_error_envelope(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    err = AnalyzeError(
        code="unreadable_image", message="bad bytes", recovery_hint="re-export"
    )
    store.set_failed(app_id, err)
    app = store.get_application(app_id)
    assert app is not None
    assert app.processing_status == ApplicationProcessingStatus.FAILED
    assert app.error is not None
    assert app.error.code == "unreadable_image"
    assert app.error.message == "bad bytes"
    assert app.processed_at is not None


# ---------------------------------------------------------------------------
# Workflow status (analyst decisions)
# ---------------------------------------------------------------------------
def test_set_workflow_status_returns_true_on_success(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]

    assert store.set_workflow_status(app_id, WorkflowStatus.REJECTED, "no") is True
    app = store.get_application(app_id)
    assert app is not None
    assert app.workflow_status == WorkflowStatus.REJECTED
    assert app.decided_note == "no"
    assert app.decided_at is not None


def test_set_workflow_status_returns_false_for_unknown_id(store: BatchStore) -> None:
    assert (
        store.set_workflow_status("app_missing", WorkflowStatus.APPROVED) is False
    )


def test_set_workflow_status_overwrites_previous(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    store.set_workflow_status(app_id, WorkflowStatus.APPROVED)
    store.set_workflow_status(app_id, WorkflowStatus.NEEDS_CORRECTION, "redo")
    app = store.get_application(app_id)
    assert app is not None
    assert app.workflow_status == WorkflowStatus.NEEDS_CORRECTION
    assert app.decided_note == "redo"


# ---------------------------------------------------------------------------
# Bulk approve
# ---------------------------------------------------------------------------
def test_bulk_approve_updates_only_pending_review(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1"), _app("A2"), _app("A3")],
    )
    app_ids = store.list_pending_application_ids(batch_id)

    # All three are clean; pre-decide A2 as REJECTED so it must be skipped.
    for aid in app_ids:
        store.set_done(aid, _make_clean_response())
    store.set_workflow_status(app_ids[1], WorkflowStatus.REJECTED)

    n = store.bulk_approve_eligible(batch_id, eligible_app_ids=list(app_ids))
    assert n == 2  # A1 + A3 only
    detail = store.get_batch_detail(batch_id)
    assert detail is not None
    statuses = {a.id: a.workflow_status for a in detail.applications}
    assert statuses[app_ids[0]] == WorkflowStatus.APPROVED
    assert statuses[app_ids[1]] == WorkflowStatus.REJECTED
    assert statuses[app_ids[2]] == WorkflowStatus.APPROVED


def test_bulk_approve_with_empty_list_is_zero(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    assert store.bulk_approve_eligible(batch_id, eligible_app_ids=[]) == 0


# ---------------------------------------------------------------------------
# is_eligible_for_bulk_approve
# ---------------------------------------------------------------------------
def test_eligibility_clean_match_is_eligible(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    store.set_done(app_id, _make_clean_response())
    app = store.get_application(app_id)
    assert app is not None
    assert is_eligible_for_bulk_approve(app) is True


def test_eligibility_blocked_by_low_confidence(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    store.set_done(app_id, _make_clean_response(all_high=False))
    app = store.get_application(app_id)
    assert app is not None
    assert is_eligible_for_bulk_approve(app) is False


def test_eligibility_blocked_by_mismatch(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    store.set_done(app_id, _make_clean_response(all_match=False))
    app = store.get_application(app_id)
    assert app is not None
    assert is_eligible_for_bulk_approve(app) is False


def test_eligibility_blocked_when_pipeline_not_done(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    app = store.get_application(app_id)
    assert app is not None
    assert is_eligible_for_bulk_approve(app) is False


def test_eligibility_blocked_when_already_decided(store: BatchStore) -> None:
    batch_id = store.create_batch(
        importer_name="Acme",
        importer_email="ops@acme.com",
        note=None,
        applications=[_app("A1")],
    )
    app_id = store.list_pending_application_ids(batch_id)[0]
    store.set_done(app_id, _make_clean_response())
    store.set_workflow_status(app_id, WorkflowStatus.APPROVED)
    app = store.get_application(app_id)
    assert app is not None
    assert is_eligible_for_bulk_approve(app) is False


# ---------------------------------------------------------------------------
# Migrations are idempotent
# ---------------------------------------------------------------------------
def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "x.db"
    s = BatchStore(db)
    s.apply_migrations()
    s.apply_migrations()  # second call must not raise

    # And we can still create a batch.
    bid = s.create_batch(
        importer_name="One",
        importer_email="one@example.com",
        note=None,
        applications=[_app("A1")],
    )
    assert s.get_batch_detail(bid) is not None


# Placate ruff about unused import of json
_ = json
