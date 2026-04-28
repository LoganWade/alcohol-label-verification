"""Integration tests for the FastAPI app.

The analyze endpoint is exercised against the stub OCR provider so the full
pipeline (preprocess -> OCR -> field extraction -> comparison -> warning
validation -> reporting) runs end-to-end without requiring real OCR weights.
"""

from __future__ import annotations

import io
import json

from app.core.constants import FieldStatus, ReviewStatus

# A 1x1 white RGB PNG — the smallest well-formed file we can submit to satisfy
# multipart requirements. Generated via Pillow; verified to decode cleanly.
# (Phase 2 note: the real preprocess stage decodes this, so the bytes must be
# a valid image, not just a PNG magic-byte stub.)
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc"
    b"\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xefF\xb8\x00\x00\x00\x00"
    b"IEND\xaeB`\x82"
)


class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["ocr_provider"] == "stub"
        assert body["ocr_model_loaded"] is True


class TestAnalyzeHappyPath:
    def test_clean_match_with_stub(self, client):
        expected = {
            "brand_name": "Old Tom Distillery",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol.",
            "net_contents": "750 mL",
            "bottler": "Bottled by Old Tom Co., Frankfort, KY",
        }
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(_PNG_1x1), "image/png")},
            data={"expected_fields": json.dumps(expected)},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        # Response shape sanity
        assert body["review_id"].startswith("rev_")
        assert "summary" in body
        assert "extracted_fields" in body
        assert "field_comparisons" in body
        assert "warning_validation" in body
        assert "processing" in body

        # Summary should be Pass given the stub matches the expected values.
        assert body["summary"]["status"] == ReviewStatus.PASS.value

        # Warning validator should report a Match with caps + wording OK.
        warning = body["warning_validation"]
        assert warning["status"] == FieldStatus.MATCH.value
        assert warning["header_caps_ok"] is True
        assert warning["wording_match"] is True

        # Brand comparison surfaces the case-only difference as Match
        # (this is the Stone's Throw rule applied via the stub).
        brand = next(c for c in body["field_comparisons"] if c["field"] == "brand_name")
        assert brand["status"] == FieldStatus.MATCH.value


class TestAnalyzeValidation:
    def test_unsupported_media_type(self, client):
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("a.gif", io.BytesIO(b"GIF89a"), "image/gif")},
            data={"expected_fields": "{}"},
        )
        assert response.status_code == 415
        assert response.json()["detail"]["code"] == "unsupported_media_type"

    def test_invalid_expected_fields_json(self, client):
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(_PNG_1x1), "image/png")},
            data={"expected_fields": "{not valid json"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_expected_fields_json"

    def test_invalid_expected_fields_schema(self, client):
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(_PNG_1x1), "image/png")},
            data={"expected_fields": json.dumps({"unknown_field": "x"})},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_expected_fields_schema"

    def test_empty_file(self, client):
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(b""), "image/png")},
            data={"expected_fields": "{}"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "empty_file"


class TestStatusVocabulary:
    """The fixed status vocabulary must round-trip through the API verbatim."""

    def test_status_strings_are_canonical(self, client):
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(_PNG_1x1), "image/png")},
            data={
                "expected_fields": json.dumps(
                    {"brand_name": "Acme Brand That Does Not Match"}
                )
            },
        )
        assert response.status_code == 200
        body = response.json()
        allowed = {"Match", "Mismatch", "Missing", "Needs Review", "Uncertain"}
        for comp in body["field_comparisons"]:
            assert comp["status"] in allowed
        assert body["warning_validation"]["status"] in allowed
        assert body["summary"]["status"] in {"Pass", "Mismatch", "Needs Review"}
