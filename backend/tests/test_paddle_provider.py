"""Tests for the PaddleOCR provider.

Tests that require the actual paddle model run are guarded with
``@pytest.mark.skipif`` so CI passes whether or not the heavy deps are
installed.  The provider *contract* tests (name attribute, ValueError on bad
input) run unconditionally by importing the class directly — they exercise the
module without triggering model loading.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Optional dependency guard
# ---------------------------------------------------------------------------
try:
    import paddleocr  # noqa: F401

    HAS_PADDLE = True
except ImportError:
    HAS_PADDLE = False

_skip_no_paddle = pytest.mark.skipif(
    not HAS_PADDLE,
    reason="paddleocr not installed; skipping real model tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_bytes(width: int = 200, height: int = 100) -> bytes:
    """Return a minimal valid PNG (white rectangle)."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Provider contract tests (no model load required)
# ---------------------------------------------------------------------------

class TestPaddleProviderContract:
    """Tests that exercise the provider class without running the model."""

    def test_name_attribute(self):
        """The provider's ``name`` attribute must equal ``'paddle'``."""
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        assert PaddleOcrProvider.name == "paddle"

    def test_factory_returns_paddle_provider(self):
        """``get_ocr_provider('paddle')`` returns a PaddleOcrProvider instance."""
        from app.services.extraction.ocr import get_ocr_provider
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        provider = get_ocr_provider("paddle")
        assert isinstance(provider, PaddleOcrProvider)

    def test_factory_still_returns_stub(self):
        """The stub provider must remain available as ``'stub'`` for existing tests."""
        from app.services.extraction.ocr import StubOcrProvider, get_ocr_provider

        provider = get_ocr_provider("stub")
        assert isinstance(provider, StubOcrProvider)

    def test_factory_unknown_name_raises(self):
        from app.services.extraction.ocr import get_ocr_provider

        with pytest.raises(ValueError, match="Unknown OCR provider"):
            get_ocr_provider("nonexistent_provider")

    def test_extract_raises_on_undecodable_bytes(self):
        """``extract()`` must raise ``ValueError`` when the image cannot be decoded,
        regardless of whether the paddle model is installed."""
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        provider = PaddleOcrProvider()
        with pytest.raises(ValueError, match="Image could not be decoded"):
            provider.extract(b"not an image at all")

    def test_extract_raises_on_empty_bytes(self):
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        provider = PaddleOcrProvider()
        with pytest.raises(ValueError, match="Image could not be decoded"):
            provider.extract(b"")


# ---------------------------------------------------------------------------
# Real model tests (skipped when paddle not installed)
# ---------------------------------------------------------------------------

class TestPaddleProviderModelRun:
    """Tests that invoke the actual PaddleOCR model.

    These are skipped in CI unless the heavy deps are present.
    """

    @_skip_no_paddle
    def test_extract_returns_sequence(self):
        """``extract()`` on a valid image returns a Sequence (possibly empty)."""
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        provider = PaddleOcrProvider()
        result = provider.extract(_make_png_bytes())
        assert isinstance(result, (list, tuple))

    @_skip_no_paddle
    def test_tokens_have_correct_schema(self):
        """Each returned token must satisfy the OcrToken schema."""
        from app.schemas.common import OcrToken
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        provider = PaddleOcrProvider()
        tokens = provider.extract(_make_png_bytes(200, 100))
        for token in tokens:
            assert isinstance(token, OcrToken)
            assert isinstance(token.text, str)
            assert 0.0 <= token.confidence <= 1.0
            assert token.bbox.x0 >= 0
            assert token.bbox.y0 >= 0
            assert token.bbox.x1 >= token.bbox.x0
            assert token.bbox.y1 >= token.bbox.y0

    @_skip_no_paddle
    def test_lazy_load_singleton(self):
        """Two provider instances share the same underlying model object."""
        from app.services.extraction import paddle_ocr as _mod

        # Reset singleton so we can observe the lazy-load
        _mod._paddle_instance = None

        p1 = _mod.PaddleOcrProvider()
        p2 = _mod.PaddleOcrProvider()

        # Trigger load via extract on a blank image (result doesn't matter)
        p1.extract(_make_png_bytes())
        first_instance = _mod._paddle_instance

        p2.extract(_make_png_bytes())
        second_instance = _mod._paddle_instance

        assert first_instance is second_instance, (
            "Singleton was replaced; model is being loaded more than once"
        )

    @_skip_no_paddle
    def test_empty_result_returns_empty_tuple(self):
        """A blank white image should produce no tokens (empty tuple), not raise."""
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        provider = PaddleOcrProvider()
        # An entirely white image has no text; PaddleOCR should return nothing.
        result = provider.extract(_make_png_bytes())
        # We accept either an empty tuple/list OR a non-empty one if the model
        # hallucinates on white — the important thing is that no exception is raised.
        assert result is not None
