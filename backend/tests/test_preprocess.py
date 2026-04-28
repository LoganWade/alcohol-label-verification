"""Tests for the Phase 2 preprocess stage.

All test images are synthesised in-test using Pillow so the suite has
no external file dependencies and runs without sample data.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.core.constants import ImageQuality
from app.services.extraction.preprocess import preprocess

# ---------------------------------------------------------------------------
# Helpers -- synthetic image builders
# ---------------------------------------------------------------------------

def _make_png(
    width: int = 800,
    height: int = 600,
    bg_color: tuple[int, int, int] = (255, 255, 255),
    text_color: tuple[int, int, int] = (0, 0, 0),
    blur_radius: float = 0.0,
) -> bytes:
    """Return PNG bytes for a simple white-background image with a black patch.

    The black patch guarantees that the Laplacian sees a sharp edge and the
    grayscale std-dev sees meaningful contrast -- giving us a controllable way
    to produce GOOD, FAIR, and POOR images.
    """
    img = Image.new("RGB", (width, height), bg_color)
    # Draw a block of text_color to introduce contrast & edges
    draw = ImageDraw.Draw(img)
    draw.rectangle([width // 4, height // 4, 3 * width // 4, 3 * height // 4], fill=text_color)

    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_low_contrast_png(width: int = 800, height: int = 600) -> bytes:
    """Return a very low-contrast PNG (text near-same colour as background)."""
    # Per spec: text RGB ~(180,180,180) on (200,200,200)
    bg = (200, 200, 200)
    text = (180, 180, 180)
    return _make_png(width=width, height=height, bg_color=bg, text_color=text)


# ---------------------------------------------------------------------------
# Basic contract tests
# ---------------------------------------------------------------------------

class TestPreprocessContract:
    def test_returns_preprocessoutput_with_quality_report(self):
        data = _make_png()
        out = preprocess(data)
        assert out.quality_report is not None
        assert out.processed_image is not None

    def test_processed_image_is_valid_png(self):
        """Output bytes must decode back to a valid image (roundtrip)."""
        data = _make_png(width=400, height=300)
        out = preprocess(data)
        decoded = Image.open(io.BytesIO(out.processed_image))
        assert decoded.width > 0
        assert decoded.height > 0

    def test_dimensions_in_report(self):
        data = _make_png(width=400, height=300)
        out = preprocess(data)
        # Report dimensions match the (possibly resized) output image
        assert out.quality_report.width > 0
        assert out.quality_report.height > 0

    def test_blur_and_contrast_scores_are_positive(self):
        data = _make_png()
        out = preprocess(data)
        assert out.quality_report.blur_score >= 0.0
        assert out.quality_report.contrast_score >= 0.0


# ---------------------------------------------------------------------------
# Quality tier tests
# ---------------------------------------------------------------------------

class TestQualityTiers:
    def test_clean_image_returns_good_quality(self):
        """A clean 800x600 image with strong black-on-white text -> GOOD."""
        data = _make_png(width=800, height=600)
        out = preprocess(data)
        assert out.quality_report.quality == ImageQuality.GOOD, (
            f"Expected GOOD, got {out.quality_report.quality}; "
            f"blur={out.quality_report.blur_score:.1f}, "
            f"contrast={out.quality_report.contrast_score:.1f}"
        )

    def test_heavily_blurred_image_returns_poor_or_fair(self):
        """A Gaussian-blurred image (kernel ~21) should be POOR or at most FAIR."""
        data = _make_png(width=800, height=600, blur_radius=10.5)  # radius approx kernel/2
        out = preprocess(data)
        assert out.quality_report.quality in (ImageQuality.POOR, ImageQuality.FAIR), (
            f"Expected POOR or FAIR, got {out.quality_report.quality}; "
            f"blur={out.quality_report.blur_score:.1f}"
        )

    def test_low_contrast_image_returns_poor(self):
        """Near-identical foreground/background colours should yield POOR quality."""
        data = _make_low_contrast_png()
        out = preprocess(data)
        assert out.quality_report.quality == ImageQuality.POOR, (
            f"Expected POOR, got {out.quality_report.quality}; "
            f"contrast={out.quality_report.contrast_score:.1f}"
        )

    def test_poor_quality_has_notes(self):
        """POOR-quality images must have at least one explanatory note."""
        data = _make_low_contrast_png()
        out = preprocess(data)
        assert out.quality_report.quality == ImageQuality.POOR
        assert len(out.quality_report.notes) > 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestPreprocessErrors:
    def test_garbage_bytes_raises_value_error(self):
        """Undecodable bytes must raise ValueError, not propagate internal exceptions."""
        with pytest.raises(ValueError, match="Image could not be decoded"):
            preprocess(b"this is not an image at all \x00\xff\xfe")

    def test_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="Image could not be decoded"):
            preprocess(b"")

    def test_truncated_png_raises_value_error(self):
        """A truncated PNG header should also raise ValueError."""
        with pytest.raises(ValueError, match="Image could not be decoded"):
            preprocess(b"\\x89PNG\\r\\n\\x1a\\n")  # PNG magic + 8 bytes only


# ---------------------------------------------------------------------------
# Resize behaviour
# ---------------------------------------------------------------------------

class TestResizeBehaviour:
    def test_large_image_is_resized(self):
        """Images wider than 1600 px should be resized in the output."""
        # Create a 2400x1800 image (long edge = 2400)
        data = _make_png(width=2400, height=1800)
        out = preprocess(data)
        report = out.quality_report
        # Long edge must not exceed MAX_LONG_EDGE_PX after preprocessing
        assert max(report.width, report.height) <= 1600

    def test_small_image_is_not_upscaled(self):
        """Images smaller than 1600 px must not be upscaled."""
        data = _make_png(width=320, height=240)
        out = preprocess(data)
        report = out.quality_report
        assert report.width <= 320
        assert report.height <= 240

    def test_aspect_ratio_preserved(self):
        """After resize, the aspect ratio must be preserved within 1%."""
        data = _make_png(width=2400, height=1800)
        original_ratio = 2400 / 1800
        out = preprocess(data)
        resized_ratio = out.quality_report.width / out.quality_report.height
        assert abs(resized_ratio - original_ratio) < 0.01, (
            f"Aspect ratio changed: {original_ratio:.3f} -> {resized_ratio:.3f}"
        )
