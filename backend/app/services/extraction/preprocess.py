"""Preprocess stage: image quality assessment, EXIF correction, resize, encode.

Operations performed (in order):
1. Decode bytes via Pillow to honour embedded EXIF orientation.
2. Convert to a numpy/OpenCV array for metric computation.
3. Compute blur score (Laplacian variance) and contrast score (grayscale std-dev).
4. Estimate skew angle via ``cv2.minAreaRect`` on a Canny-edge binary mask.
5. Resize so the long edge is at most MAX_LONG_EDGE_PX (1600 px), preserving
   aspect ratio.
6. PNG-encode the result and return it alongside an ``ImageQualityReport``.

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
    # 5. Resize so the long edge <= MAX_LONG_EDGE_PX (preserve aspect)
    # ------------------------------------------------------------------
    img_bgr = _resize_long_edge(img_bgr, MAX_LONG_EDGE_PX)
    out_h, out_w = img_bgr.shape[:2]

    # ------------------------------------------------------------------
    # 6. Determine quality tier and build notes
    # ------------------------------------------------------------------
    notes: list[str] = []
    quality = _assess_quality(blur_score, contrast_score, notes)

    # ------------------------------------------------------------------
    # 7. PNG-encode the processed image
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

    # minAreaRect returns (center, (w, h), angle).  The angle is in the
    # range (-90, 0] for OpenCV < 4.5 and may differ in later versions;
    # we normalise to (-45, 45] which covers practical skew cases.
    rect = cv2.minAreaRect(points)
    angle: float = float(rect[2])

    # Normalise: OpenCV encodes near-vertical rectangles with angle near -90
    if angle < -45.0:
        angle += 90.0
    return round(angle, 2)


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
