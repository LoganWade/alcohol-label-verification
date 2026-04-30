"""End-to-end tests for the batch upload API.

These tests exercise the FastAPI app via TestClient. They cover the
multipart submission flow, validation errors (manifest, missing
images, wrong content type), the read endpoints, the analyst
decision PUT, and the bulk-approve POST. The pipeline runs against
the stub OCR provider so the whole chain is exercised without
PaddleOCR weights.
"""

from __future__ import annotations

import io
import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.services.batch import storage as storage_module


# ---------------------------------------------------------------------------
# Test setup: isolate every test from the shared singleton + filesystem
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the BatchStore singleton + the storage dir at tmp_path.

    The fixture is autouse so every test in this file gets a fresh DB
    and a fresh upload directory; tests cannot leak rows or files into
    each other.
    """

    db_path = tmp_path / "batches.db"
    storage_dir = tmp_path / "uploads"
    storage_dir.mkdir()

    # The settings module is imported once at process start; mutate it.
    from app.core.settings import settings

    monkeypatch.setattr(settings, "batch_db_path", str(db_path))
    monkeypatch.setattr(settings, "batch_storage_dir", str(storage_dir))

    # Reset the cached singleton and re-create against the new path.
    storage_module._store_singleton = None  # type: ignore[attr-defined]
    storage_module.reset_store_for_tests(db_path)
    yield
    storage_module._store_singleton = None  # type: ignore[attr-defined]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _png_bytes(*, w: int = 64, h: int = 64, color: str = "white") -> bytes:
    """Produce a small, real PNG. The preprocess stage prefers something
    bigger than 1x1; the stub OCR pipeline does not care about content."""

    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _manifest_csv(*rows: str) -> bytes:
    header = (
        "serial_number,brand_name,class_type,alcohol_content,net_contents,"
        "bottler,country_of_origin,image_filename,attribution,is_primary"
    )
    return ("\n".join((header, *rows)) + "\n").encode("utf-8")


_DEFAULT_ROW = "A1,B,C,40%,750mL,X,US,A1.png,front,true"


def _wait_for_processing(
    client: TestClient, batch_id: str, *, timeout_s: float = 5.0
) -> dict:
    """Poll GET /batches/{id} until counts.pending + counts.processing == 0."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/v1/batches/{batch_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        c = body["counts"]
        if c["pending"] == 0 and c["processing"] == 0:
            return body
        time.sleep(0.05)
    raise AssertionError(
        f"timed out waiting for batch {batch_id} to finish processing"
    )


def _submit_simple_batch(
    client: TestClient,
    *,
    serials: tuple[str, ...] = ("A1",),
    importer_email: str = "ops@acme.com",
) -> str:
    """Helper: submit a small clean batch and return its id."""

    rows = [
        f"{s},Brand X,Vodka,40%,750 mL,Acme,USA,{s}.png,front,true"
        for s in serials
    ]
    manifest = _manifest_csv(*rows)
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("manifest", ("manifest.csv", manifest, "text/csv")),
    ]
    for s in serials:
        files.append(("images", (f"{s}.png", _png_bytes(), "image/png")))
    meta = json.dumps(
        {"importer_name": "Acme", "importer_email": importer_email, "note": "demo"}
    )
    r = client.post("/api/v1/batches", data={"meta": meta}, files=files)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# POST /batches happy path
# ---------------------------------------------------------------------------
def test_post_batch_creates_and_returns_summary(client: TestClient) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1", "A2"))
    assert batch_id.startswith("bat_")

    body = _wait_for_processing(client, batch_id)
    assert body["importer_name"] == "Acme"
    assert body["counts"]["total"] == 2
    assert body["counts"]["pending"] + body["counts"]["processing"] == 0
    # Pipeline ran on stub OCR; we only assert the lifecycle finished.
    assert body["counts"]["done"] + body["counts"]["failed"] == 2


def test_post_batch_persists_images_on_disk(
    client: TestClient, tmp_path: Path
) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app = body["applications"][0]
    # Filename is preserved in the response; physical file lives under
    # the configured batch_storage_dir.
    from app.core.settings import settings

    storage_root = Path(settings.batch_storage_dir)
    files = list(storage_root.rglob("A1.png"))
    assert files, f"no A1.png under {storage_root}"
    assert files[0].stat().st_size > 0
    assert app["images"][0]["filename"] == "A1.png"


# ---------------------------------------------------------------------------
# POST /batches validation
# ---------------------------------------------------------------------------
def test_post_batch_rejects_invalid_meta_json(client: TestClient) -> None:
    files = [
        ("manifest", ("m.csv", _manifest_csv(_DEFAULT_ROW), "text/csv")),
        ("images", ("A1.png", _png_bytes(), "image/png")),
    ]
    r = client.post(
        "/api/v1/batches", data={"meta": "{not json"}, files=files
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_meta_json"


def test_post_batch_rejects_invalid_meta_schema(client: TestClient) -> None:
    files = [
        ("manifest", ("m.csv", _manifest_csv(_DEFAULT_ROW), "text/csv")),
        ("images", ("A1.png", _png_bytes(), "image/png")),
    ]
    r = client.post(
        "/api/v1/batches",
        data={"meta": json.dumps({"importer_email": "no name"})},
        files=files,
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_meta_schema"


def test_post_batch_rejects_bad_email(client: TestClient) -> None:
    files = [
        ("manifest", ("m.csv", _manifest_csv(_DEFAULT_ROW), "text/csv")),
        ("images", ("A1.png", _png_bytes(), "image/png")),
    ]
    r = client.post(
        "/api/v1/batches",
        data={
            "meta": json.dumps(
                {"importer_name": "Acme", "importer_email": "not an email"}
            )
        },
        files=files,
    )
    assert r.status_code == 400


def test_post_batch_returns_all_manifest_errors(client: TestClient) -> None:
    bad_csv = _manifest_csv(
        "A1,Brand X,Vodka,40%,750mL,Acme,USA,a.png,front,maybe",
        ",Brand X,Vodka,40%,750mL,Acme,USA,b.png,front,true",
    )
    files = [
        ("manifest", ("m.csv", bad_csv, "text/csv")),
        ("images", ("a.png", _png_bytes(), "image/png")),
        ("images", ("b.png", _png_bytes(), "image/png")),
    ]
    r = client.post(
        "/api/v1/batches",
        data={
            "meta": json.dumps(
                {"importer_name": "Acme", "importer_email": "ops@acme.com"}
            )
        },
        files=files,
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_manifest"
    codes = {e["code"] for e in detail["manifest_errors"]}
    assert "row_invalid_is_primary" in codes
    assert "row_missing_serial" in codes


def test_post_batch_rejects_unsupported_image_type(client: TestClient) -> None:
    files = [
        (
            "manifest",
            ("m.csv", _manifest_csv("A1,B,C,40%,750mL,X,US,A1.bmp,front,true"), "text/csv"),
        ),
        ("images", ("A1.bmp", b"BM" + b"\x00" * 100, "image/bmp")),
    ]
    r = client.post(
        "/api/v1/batches",
        data={
            "meta": json.dumps(
                {"importer_name": "Acme", "importer_email": "ops@acme.com"}
            )
        },
        files=files,
    )
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "unsupported_image_type"


def test_post_batch_reports_missing_image_files(client: TestClient) -> None:
    files = [
        (
            "manifest",
            ("m.csv", _manifest_csv("A1,B,C,40%,750mL,X,US,A1.png,front,true"), "text/csv"),
        ),
        ("images", ("WRONG_NAME.png", _png_bytes(), "image/png")),
    ]
    r = client.post(
        "/api/v1/batches",
        data={
            "meta": json.dumps(
                {"importer_name": "Acme", "importer_email": "ops@acme.com"}
            )
        },
        files=files,
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] in {"missing_images", "extra_images"}


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------
def test_get_batches_returns_created_batch(client: TestClient) -> None:
    batch_id = _submit_simple_batch(client)
    _wait_for_processing(client, batch_id)
    r = client.get("/api/v1/batches")
    assert r.status_code == 200
    ids = {b["id"] for b in r.json()}
    assert batch_id in ids


def test_get_batch_detail_404_for_unknown(client: TestClient) -> None:
    r = client.get("/api/v1/batches/bat_does_not_exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "batch_not_found"


def test_get_application_404_for_unknown(client: TestClient) -> None:
    r = client.get("/api/v1/applications/app_does_not_exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "application_not_found"


def test_get_application_returns_analyze_when_done(client: TestClient) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app_id = body["applications"][0]["id"]
    r = client.get(f"/api/v1/applications/{app_id}")
    assert r.status_code == 200
    payload = r.json()
    # Pipeline either succeeded (analyze present) or failed cleanly (error).
    assert payload["processing_status"] in {"done", "failed"}
    if payload["processing_status"] == "done":
        assert payload["analyze"] is not None
        assert payload["analyze"]["summary"]["status"] in {
            "Pass",
            "Mismatch",
            "Needs Review",
        }


# ---------------------------------------------------------------------------
# PUT /applications/{id}/decision
# ---------------------------------------------------------------------------
def test_put_decision_updates_workflow_status(client: TestClient) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app_id = body["applications"][0]["id"]

    r = client.put(
        f"/api/v1/applications/{app_id}/decision",
        json={"workflow_status": "rejected", "note": "blurry"},
    )
    assert r.status_code == 200
    assert r.json()["workflow_status"] == "rejected"
    assert r.json()["decided_note"] == "blurry"

    # Round-trip via GET.
    r = client.get(f"/api/v1/applications/{app_id}")
    assert r.json()["workflow_status"] == "rejected"


def test_put_decision_404_for_unknown(client: TestClient) -> None:
    r = client.put(
        "/api/v1/applications/app_nope/decision",
        json={"workflow_status": "approved"},
    )
    assert r.status_code == 404


def test_put_decision_rejects_unknown_status(client: TestClient) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app_id = body["applications"][0]["id"]
    r = client.put(
        f"/api/v1/applications/{app_id}/decision",
        json={"workflow_status": "approved_with_caveats"},
    )
    assert r.status_code == 422  # Pydantic enum validation


# ---------------------------------------------------------------------------
# POST /batches/{id}/bulk-approve
# ---------------------------------------------------------------------------
def test_bulk_approve_returns_counts_and_skipped_reasons(
    client: TestClient,
) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1", "A2"))
    _wait_for_processing(client, batch_id)
    r = client.post(f"/api/v1/batches/{batch_id}/bulk-approve")
    assert r.status_code == 200
    body = r.json()
    assert "approved_count" in body
    assert "skipped_count" in body
    assert "skipped_reasons" in body
    # Stub OCR pipeline rarely produces all-HIGH all-MATCH on a blank
    # white image, so we don't assert approved_count > 0; we only assert
    # the response shape.


def test_bulk_approve_404_for_unknown_batch(client: TestClient) -> None:
    r = client.post("/api/v1/batches/bat_nope/bulk-approve")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /applications/{id}/images/{image_id}
# ---------------------------------------------------------------------------
def test_get_application_image_returns_png_bytes(client: TestClient) -> None:
    """The image route returns the PNG bytes the importer uploaded."""

    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app = body["applications"][0]
    image = app["images"][0]
    r = client.get(
        f"/api/v1/applications/{app['id']}/images/{image['id']}"
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert len(r.content) > 0
    # PNG magic bytes
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_get_application_image_404_for_unknown_image(client: TestClient) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app_id = body["applications"][0]["id"]
    r = client.get(f"/api/v1/applications/{app_id}/images/img_does_not_exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "image_not_found"


def test_get_application_image_404_for_unknown_application(
    client: TestClient,
) -> None:
    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    image_id = body["applications"][0]["images"][0]["id"]
    r = client.get(f"/api/v1/applications/app_unknown/images/{image_id}")
    assert r.status_code == 404


def test_get_application_image_rejects_cross_application_id(
    client: TestClient,
) -> None:
    """Using one application's id with another application's image id
    must 404 — the (application_id, image_id) pair is required to match.
    """

    batch_id = _submit_simple_batch(client, serials=("A1", "A2"))
    body = _wait_for_processing(client, batch_id)
    app_a, app_b = body["applications"][0], body["applications"][1]
    # image belongs to app_a; request it under app_b's id
    r = client.get(
        f"/api/v1/applications/{app_b['id']}/images/{app_a['images'][0]['id']}"
    )
    assert r.status_code == 404


def test_get_application_image_404_when_file_missing_on_disk(
    client: TestClient,
) -> None:
    """If the DB row exists but the on-disk file is gone, return 404
    instead of crashing."""

    from app.core.settings import settings

    batch_id = _submit_simple_batch(client, serials=("A1",))
    body = _wait_for_processing(client, batch_id)
    app = body["applications"][0]
    # Delete the image bytes from disk
    storage_root = Path(settings.batch_storage_dir)
    for f in storage_root.rglob("A1.png"):
        f.unlink()
    r = client.get(
        f"/api/v1/applications/{app['id']}/images/{app['images'][0]['id']}"
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "image_not_found"
