"""Tests for the field extractor's spatial heuristics.

The extractor takes OCR tokens (one per text line on a TTB label) and folds
them into the seven supported fields. The interesting cases are multi-line
fields like the Government Warning, where PaddleOCR returns one token per
visual line and the extractor has to stitch them back together.
"""

from __future__ import annotations

from app.core.constants import Confidence
from app.schemas.common import BoundingBox, OcrToken
from app.schemas.fields import FieldName
from app.services.extraction.field_extraction import extract_fields


def _token(text: str, y0: int, y1: int, confidence: float = 0.95) -> OcrToken:
    """Build an OCR token at the given vertical band, full label width."""
    return OcrToken(
        text=text,
        bbox=BoundingBox(x0=50, y0=y0, x1=750, y1=y1),
        confidence=confidence,
    )


class TestWarningMultiLineStitching:
    """Regression tests for the skewed_lowlight bug.

    PaddleOCR returns one token per visual line. The Government Warning
    paragraph spans 4-5 lines on a typical TTB label. The extractor must
    stitch all consecutive lines starting at the "GOVERNMENT WARNING"
    anchor into a single warning field; otherwise the validator only sees
    the header and reports a 71% wording-similarity score.
    """

    def test_stitches_consecutive_warning_lines(self):
        # Realistic TTB warning split across five lines, top-to-bottom.
        tokens = [
            _token("STONE'S THROW WINERY", y0=50, y1=120),
            _token("Cabernet Sauvignon", y0=140, y1=190),
            _token("13.5% Alc./Vol.", y0=200, y1=250),
            _token("750 mL", y0=200, y1=250),
            _token(
                "GOVERNMENT WARNING: (1) According to the Surgeon General,",
                y0=400,
                y1=440,
            ),
            _token(
                "women should not drink alcoholic beverages during pregnancy",
                y0=445,
                y1=485,
            ),
            _token(
                "because of the risk of birth defects. (2) Consumption of",
                y0=490,
                y1=530,
            ),
            _token(
                "alcoholic beverages impairs your ability to drive a car or",
                y0=535,
                y1=575,
            ),
            _token(
                "operate machinery, and may cause health problems.",
                y0=580,
                y1=620,
            ),
        ]
        fields = extract_fields(tokens)

        assert fields.warning.raw_text is not None
        # All five warning lines must be present in the joined text.
        assert "GOVERNMENT WARNING" in fields.warning.raw_text
        assert "Surgeon General" in fields.warning.raw_text
        assert "birth defects" in fields.warning.raw_text
        assert "operate machinery" in fields.warning.raw_text

    def test_evidence_bbox_covers_full_warning_block(self):
        tokens = [
            _token("GOVERNMENT WARNING", y0=400, y1=440),
            _token("body line 1", y0=445, y1=485),
            _token("body line 2", y0=490, y1=530),
        ]
        fields = extract_fields(tokens)

        assert fields.warning.evidence_bbox is not None
        # Bbox should span from the anchor's top to the last line's bottom.
        assert fields.warning.evidence_bbox.y0 == 400
        assert fields.warning.evidence_bbox.y1 == 530

    def test_warning_block_uses_lowest_confidence_among_lines(self):
        # Header is high-confidence; one body line is low-confidence. The
        # block as a whole should report the worst confidence so the
        # validator can downgrade if any line was unsure.
        tokens = [
            _token("GOVERNMENT WARNING", y0=400, y1=440, confidence=0.98),
            _token("body line 1", y0=445, y1=485, confidence=0.55),  # LOW tier
            _token("body line 2", y0=490, y1=530, confidence=0.92),
        ]
        fields = extract_fields(tokens)
        assert fields.warning.confidence == Confidence.LOW

    def test_unrelated_text_after_a_gap_is_not_folded_into_warning(self):
        # The country-of-origin line is far below the warning block; it
        # must not be glommed in.
        tokens = [
            _token("GOVERNMENT WARNING", y0=400, y1=440),
            _token("body line 1", y0=445, y1=485),
            _token("Product of California, USA", y0=900, y1=940),
        ]
        fields = extract_fields(tokens)

        assert fields.warning.raw_text is not None
        assert "Product of California" not in fields.warning.raw_text

    def test_no_warning_token_leaves_warning_uncertain(self):
        tokens = [
            _token("STONE'S THROW WINERY", y0=50, y1=120),
            _token("Cabernet Sauvignon", y0=140, y1=190),
        ]
        fields = extract_fields(tokens)
        assert fields.warning.raw_text is None
        assert fields.warning.confidence == Confidence.UNCERTAIN
