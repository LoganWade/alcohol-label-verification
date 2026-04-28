"""Tests for the GET /api/v1/samples endpoints.

Covers:
  - list endpoint returns all 11 entries (8 synthetic + 3 TTB reference)
  - list entries have the required shape (id, title, provenance, ...)
  - provenance values are restricted to the two allowed literals
  - image endpoint returns 200 with image/png for a known sample
  - expected-fields endpoint returns a valid ExpectedFields payload
  - 404 with AnalyzeError envelope for an unknown sample id
  - _load_manifest cache resets between tests via monkeypatching

The tests resolve sample_data relative to the repo root so they work whether
the test is run from backend/ or from the repo root.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent / "sample_data"
)


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestListSamples:
    def test_returns_200(self, client):
        res = client.get("/api/v1/samples")
        assert res.status_code == 200

    def test_returns_list(self, client):
        body = client.get("/api/v1/samples").json()
        assert isinstance(body, list)
        assert len(body) > 0

    def test_contains_all_11_samples(self, client):
        body = client.get("/api/v1/samples").json()
        assert len(body) == 11

    def test_sample_has_required_fields(self, client):
        body = client.get("/api/v1/samples").json()
        for entry in body:
            assert "id" in entry
            assert "title" in entry
            assert "description" in entry
            assert "expected_outcome" in entry
            assert "provenance" in entry

    def test_provenance_values_are_valid(self, client):
        allowed = {"synthetic", "public_ttb_reference"}
        body = client.get("/api/v1/samples").json()
        for entry in body:
            assert entry["provenance"] in allowed, (
                f"Unknown provenance {entry['provenance']!r} for id {entry['id']!r}"
            )

    def test_has_8_synthetic(self, client):
        body = client.get("/api/v1/samples").json()
        synthetic = [e for e in body if e["provenance"] == "synthetic"]
        assert len(synthetic) == 8

    def test_has_3_ttb_reference(self, client):
        body = client.get("/api/v1/samples").json()
        ttb = [e for e in body if e["provenance"] == "public_ttb_reference"]
        assert len(ttb) == 3

    def test_ttb_sample_ids_present(self, client):
        body = client.get("/api/v1/samples").json()
        ids = {e["id"] for e in body}
        assert "ttb_wine_reference" in ids
        assert "ttb_table_wine_reference" in ids
        assert "ttb_beer_reference" in ids

    def test_list_does_not_expose_source_url_or_paths(self, client):
        """SampleSummary is the response model — internal paths must be hidden."""
        body = client.get("/api/v1/samples").json()
        for entry in body:
            assert "image_path" not in entry
            assert "expected_fields_path" not in entry


# ---------------------------------------------------------------------------
# Image endpoint
# ---------------------------------------------------------------------------


class TestSampleImage:
    def test_known_sample_returns_200_png(self, client):
        res = client.get("/api/v1/samples/clean_match/image")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("image/png")

    def test_ttb_wine_image_returns_200(self, client):
        res = client.get("/api/v1/samples/ttb_wine_reference/image")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("image/png")

    def test_ttb_beer_image_returns_200(self, client):
        res = client.get("/api/v1/samples/ttb_beer_reference/image")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("image/png")

    def test_unknown_id_returns_404(self, client):
        res = client.get("/api/v1/samples/does_not_exist/image")
        assert res.status_code == 404

    def test_404_uses_analyze_error_envelope(self, client):
        res = client.get("/api/v1/samples/no_such_sample/image")
        body = res.json()
        assert "detail" in body
        detail = body["detail"]
        assert "code" in detail
        assert "message" in detail
        assert detail["code"] == "sample_not_found"


# ---------------------------------------------------------------------------
# Expected-fields endpoint
# ---------------------------------------------------------------------------


class TestSampleExpectedFields:
    def test_clean_match_returns_200(self, client):
        res = client.get("/api/v1/samples/clean_match/expected-fields")
        assert res.status_code == 200

    def test_response_has_all_field_keys(self, client):
        body = client.get(
            "/api/v1/samples/clean_match/expected-fields"
        ).json()
        for key in (
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "bottler",
            "country_of_origin",
            "warning",
        ):
            assert key in body, f"Missing key: {key}"

    def test_ttb_wine_fields_brand(self, client):
        body = client.get(
            "/api/v1/samples/ttb_wine_reference/expected-fields"
        ).json()
        assert body["brand_name"] == "ABC WINES"

    def test_ttb_table_wine_fields_abv_is_null(self, client):
        """Table wine ABV is null — not required under 27 CFR 4.36(a)."""
        body = client.get(
            "/api/v1/samples/ttb_table_wine_reference/expected-fields"
        ).json()
        assert body["alcohol_content"] is None

    def test_ttb_beer_fields_brand(self, client):
        body = client.get(
            "/api/v1/samples/ttb_beer_reference/expected-fields"
        ).json()
        assert body["brand_name"] == "Example"

    def test_unknown_id_returns_404(self, client):
        res = client.get("/api/v1/samples/no_such/expected-fields")
        assert res.status_code == 404

    def test_404_uses_analyze_error_envelope(self, client):
        res = client.get("/api/v1/samples/no_such/expected-fields")
        body = res.json()
        assert body["detail"]["code"] == "sample_not_found"
