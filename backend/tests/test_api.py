"""Integration tests for the FastAPI app.

The analyze endpoint is exercised against the stub OCR provider so the full
pipeline (preprocess -> OCR -> field extraction -> comparison -> warning
validation -> reporting) runs end-to-end without requiring real OCR weights.
"""

from __future__ import annotations

import io
import json

import numpy as np
from PIL import Image, ImageDraw

from app.core.constants import FieldStatus, ReviewStatus

# A 1x1 white RGB PNG — the smallest well-formed file we can submit to satisfy
# multipart requirements. Used by tests that only care about routing /
# validation, not pipeline outcomes (the preprocess stage will flag it as
# POOR quality and the pipeline will downgrade extracted-field confidence
# accordingly, which is correct behavior).
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc"
    b"\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xefF\xb8\x00\x00\x00\x00"
    b"IEND\xaeB`\x82"
)


def _build_good_quality_png() -> bytes:
    """Build a synthetic PNG that the preprocess stage classifies as GOOD.

    The preprocess quality check uses a Laplacian-variance blur score and a
    contrast/std-dev score. A solid-color image scores 0 on both. We need an
    image with sharp high-contrast edges and a wide tonal range so the test
    exercises the happy-path (non-POOR) branch of the pipeline.

    The image is generated rather than checked in so the test does not depend
    on a binary fixture file.
    """
    width, height = 480, 320
    # Start from random noise (max contrast across all pixels), then overlay
    # high-contrast text-like rectangles to push the Laplacian-variance score
    # well above the GOOD threshold.
    rng = np.random.default_rng(seed=42)
    arr = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)
    # A few sharp black-on-white bars guarantee a high blur (sharpness) score
    # regardless of any future tweaks to the noise generator.
    for y in (40, 100, 160, 220, 280):
        draw.rectangle([(20, y), (460, y + 20)], fill=(0, 0, 0))
        draw.rectangle([(20, y + 25), (460, y + 35)], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_PNG_GOOD = _build_good_quality_png()


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
        # Use a GOOD-quality synthetic PNG so the pipeline does not apply the
        # POOR-quality confidence downgrade. The downgrade is correct behavior
        # (and verified separately in test_pipeline_downgrade.py); this test
        # asserts the clean happy path.
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(_PNG_GOOD), "image/png")},
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
        # Use a sentinel value that would be obviously visible if echoed back.
        sentinel = "SENTINEL_INPUT_VALUE_xyz123"
        response = client.post(
            "/api/v1/reviews/analyze",
            files={"image": ("label.png", io.BytesIO(_PNG_1x1), "image/png")},
            data={"expected_fields": json.dumps({"unknown_field": sentinel})},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_expected_fields_schema"
        # Recovery hint must not leak the user's raw input value.
        assert sentinel not in detail["recovery_hint"]
        # It should reference the offending field name, though.
        assert "unknown_field" in detail["recovery_hint"]

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
