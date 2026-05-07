"""Preprocess stage: image quality assessment, EXIF correction, deskew, resize, encode.

Operations performed (in order):
1. Decode bytes via Pillow to honour embedded EXIF orientation.
2. Convert to a numpy/OpenCV array for metric computation.
3. Compute blur score (Laplacian variance) and contrast score (grayscale std-dev).
4. Estimate skew angle via ``cv2.minAreaRect`` on a Canny-edge binary mask.
5. If the estimated skew exceeds ``DESKEW_MIN_DEGREES``, rotate the image by
   the negative of that angle so text lines are horizontal before OCR runs.
   This materially improves PaddleOCR's line detection on phone-quality
   photos -- on the seeded ``skewed_lowlight`` sample (7° rotation) the
   warning paragraph went from "header only, 71% similarity" to the full
   five-line paragraph being captured.
6. Resize so the long edge is at most MAX_LONG_EDGE_PX (1600 px), preserving
   aspect ratio.
7. PNG-encode the result and return it alongside an ``ImageQualityReport``.

Quality thresholds (calibrated for typical phone-quality label photos):
- GOOD  : blur_score >= 100  AND  contrast_score >= 35
- FAIR  : blur_score >=  50  AND  contrast_score >= 20
- POOR  : anything decodable but below the FAIR thresholds
- FAILED: image could not be decoded — raises ValueError instead

Per AGENTS.md, uncertainty propagates forward.  ``POOR`` quality will cause the
pipeline layer to downgrade all extracted-field confidences before comparison.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.core.constants import ImageQuality
from app.schemas.pipeline import ImageQualityReport, PreprocessOutput

# ---------------------------------------------------------------------------
# Tuneable constants (single source of truth for reviewers / future tuning)
# ---------------------------------------------------------------------------
MAX_LONG_EDGE_PX: int = 1600

# Quality tier thresholds
BLUR_GOOD: float = 100.0
BLUR_FAIR: float = 50.0
CONTRAST_GOOD: float = 35.0
CONTRAST_FAIR: float = 20.0

# Deskew is only applied when the absolute estimated skew exceeds this many
# degrees. Below this, the rotation cost (resampling blur, edge artifacts)
# isn't worth the marginal OCR improvement, and the estimator's own noise
# floor is in this range. 1.0° was chosen because typical handheld phone
# photos sit at 0–1° of incidental skew that humans don't perceive as tilted
# and that PaddleOCR handles natively via use_angle_cls.
DESKEW_MIN_DEGREES: float = 1.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def preprocess(image_bytes: bytes) -> PreprocessOutput:
    """Preprocess raw uploaded image bytes.

    Returns a ``PreprocessOutput`` containing:
    - ``quality_report`` — metrics and overall quality tier.
    - ``processed_image`` — PNG-encoded bytes of the preprocessed image,
      ready to feed into the OCR provider.

    Raises:
        ValueError: if the image cannot be decoded.
    """
    if not image_bytes:
        raise ValueError("Image could not be decoded")

    # ------------------------------------------------------------------
    # 1. Decode via Pillow (honours EXIF orientation automatically via
    #    ImageOps.exif_transpose so phone photos arrive right-side up).
    # ------------------------------------------------------------------
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        pil_img = pil_img.convert("RGB")
    except Exception as exc:
        raise ValueError("Image could not be decoded") from exc

    # Convert to OpenCV BGR numpy array for metric computation
    img_bgr: np.ndarray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    # ------------------------------------------------------------------
    # 2. Blur score — variance of the Laplacian (higher = sharper)
    # ------------------------------------------------------------------
    gray: np.ndarray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur_score: float = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # ------------------------------------------------------------------
    # 3. Contrast score — standard deviation of grayscale pixel values
    # ------------------------------------------------------------------
    contrast_score: float = float(gray.std())

    # ------------------------------------------------------------------
    # 4. Skew estimation — minAreaRect on Canny edges
    #    Returns the angle of the dominant rectangular content block.
    #    We clamp to [-45, 45] degrees; values outside that range usually
    #    indicate a nearly-vertical or noisy edge map rather than skew.
    # ------------------------------------------------------------------
    estimated_skew_degrees: float = _estimate_skew(gray)

    # ------------------------------------------------------------------
    # 5. Deskew if the estimate is meaningfully non-zero. We rotate by the
    #    negative of the estimated angle, expanding the canvas so no content
    #    is clipped, and fill the new corners with white (the dominant
    #    background colour on TTB-style labels). PaddleOCR's line detector
    #    is much more reliable when text rows are horizontal, especially on
    #    multi-line paragraphs like the Government Warning.
    # ------------------------------------------------------------------
    notes: list[str] = []
    if abs(estimated_skew_degrees) >= DESKEW_MIN_DEGREES:
        img_bgr = _deskew(img_bgr, estimated_skew_degrees)
        notes.append(
            f"Deskewed by {-estimated_skew_degrees:+.2f}° to align text "
            "lines before OCR."
        )

    # ------------------------------------------------------------------
    # 6. Resize so the long edge <= MAX_LONG_EDGE_PX (preserve aspect)
    # ------------------------------------------------------------------
    img_bgr = _resize_long_edge(img_bgr, MAX_LONG_EDGE_PX)
    out_h, out_w = img_bgr.shape[:2]

    # ------------------------------------------------------------------
    # 7. Determine quality tier (appends its own notes for low blur/contrast)
    # ------------------------------------------------------------------
    quality = _assess_quality(blur_score, contrast_score, notes)

    # ------------------------------------------------------------------
    # 8. PNG-encode the processed image
    # ------------------------------------------------------------------
    success, encoded = cv2.imencode(".png", img_bgr)
    if not success:
        raise ValueError("Image could not be decoded")
    processed_bytes: bytes = encoded.tobytes()

    report = ImageQualityReport(
        quality=quality,
        width=out_w,
        height=out_h,
        estimated_skew_degrees=estimated_skew_degrees,
        blur_score=blur_score,
        contrast_score=contrast_score,
        notes=notes,
    )
    return PreprocessOutput(quality_report=report, processed_image=processed_bytes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _estimate_skew(gray: np.ndarray) -> float:
    """Estimate skew in degrees using minAreaRect on Canny edge contours.

    Returns 0.0 if there are not enough edge pixels to make a reliable
    estimate (e.g. blank or near-blank images).
    """
    edges = cv2.Canny(gray, threshold1=50, threshold2=150)
    points = np.column_stack(np.where(edges > 0))
    if len(points) < 10:
        return 0.0

    # minAreaRect returns (center, (w, h), angle). The angle convention
    # depends on OpenCV version: pre-4.5 it was in (-90, 0]; 4.5+ it's in
    # [0, 90). Either way, the *axis* (long side) of the rectangle can be
    # near-horizontal or near-vertical, and minAreaRect doesn't tell you
    # which -- so a horizontal text block on a non-skewed image can come
    # back as +90 (long side horizontal) or 0 (long side vertical),
    # ambiguously.
    #
    # We fold the angle into (-45, 45] in both directions so that a
    # horizontal bar reports ~0 skew (not 90) and a counter-clockwise tilt
    # is negative. This also stops the deskew step from rotating clean
    # images by 90 degrees, which it would otherwise do every time the
    # estimator picked the perpendicular axis.
    rect = cv2.minAreaRect(points)
    angle: float = float(rect[2])

    if angle < -45.0:
        angle += 90.0
    elif angle > 45.0:
        angle -= 90.0
    return round(angle, 2)


def _deskew(img: np.ndarray, angle_degrees: float) -> np.ndarray:
    """Rotate ``img`` by ``-angle_degrees`` to undo estimated skew.

    The rotation is around the image centre with bicubic resampling. The
    output canvas is expanded so no content is clipped, and the new corners
    are filled with white -- the dominant background colour on TTB-style
    labels, chosen so the rotated edges don't introduce a dark frame that
    the OCR detector might mistake for text.

    Args:
        img: BGR image as a numpy array.
        angle_degrees: estimated skew in degrees. We rotate by the negative
            of this so a positive estimated skew (clockwise) is undone by a
            counter-clockwise rotation.

    Returns:
        The deskewed image. May be slightly larger than the input due to
        canvas expansion.
    """
    h, w = img.shape[:2]
    centre = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(centre, -angle_degrees, scale=1.0)

    # Expand the output canvas so the rotated content fits without clipping.
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(round(h * sin + w * cos))
    new_h = int(round(h * cos + w * sin))
    matrix[0, 2] += (new_w / 2.0) - centre[0]
    matrix[1, 2] += (new_h / 2.0) - centre[1]

    return cv2.warpAffine(
        img,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _resize_long_edge(img: np.ndarray, max_px: int) -> np.ndarray:
    """Return a resized image where the long edge is at most ``max_px`` px."""
    h, w = img.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_px:
        return img
    scale = max_px / long_edge
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _assess_quality(
    blur_score: float,
    contrast_score: float,
    notes: list[str],
) -> ImageQuality:
    """Determine quality tier and populate ``notes`` with flagged conditions."""
    if blur_score >= BLUR_GOOD and contrast_score >= CONTRAST_GOOD:
        return ImageQuality.GOOD

    if blur_score >= BLUR_FAIR and contrast_score >= CONTRAST_FAIR:
        if blur_score < BLUR_GOOD:
            notes.append(
                f"Blur score {blur_score:.0f}; image may be slightly out of focus."
            )
        if contrast_score < CONTRAST_GOOD:
            notes.append(
                f"Contrast score {contrast_score:.0f}; lighting is moderate."
            )
        return ImageQuality.FAIR

    # POOR tier — flag specific conditions
    if blur_score < BLUR_FAIR:
        notes.append(
            f"Blur score {blur_score:.0f}; image may be out of focus."
        )
    if contrast_score < CONTRAST_FAIR:
        notes.append(
            f"Contrast score {contrast_score:.0f}; lighting is poor."
        )
    return ImageQuality.POOR
