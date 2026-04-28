"""PaddleOCR provider — Phase 2 real OCR implementation.

INSTALL NOTE: PaddleOCR and PaddlepadDle are heavy dependencies (~500 MB
combined). They are listed in pyproject.toml's main dependencies section and
should be pre-downloaded at Docker image build time. If the deploy container
does not have them installed, the import below will fail and the service will
raise a startup error when ``ocr_provider = "paddle"`` is configured.

If you are running locally without paddle installed, set ``ALV_OCR_PROVIDER=stub``
in your ``.env`` file (or environment) to fall back to the deterministic stub
and still exercise the full pipeline.

Per AGENTS.md:
- Raw token text is **immutable evidence** — never mutated here.
- Confidence flows forward unchanged.
- Uncertainty propagates from this stage via the confidence values we emit.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from app.schemas.common import BoundingBox, OcrToken
from app.services.extraction.ocr import OcrProvider

# Module-level singleton - instantiated lazily on first ``extract()`` call.
# PaddleOCR's constructor triggers model loading (~1-3 s); caching here means
# subsequent requests skip that cost entirely.
_paddle_instance: object | None = None


def _get_paddle() -> object:
    """Return the shared PaddleOCR instance, loading the model on first call."""
    global _paddle_instance
    if _paddle_instance is None:
        # Import deferred so the module can be *imported* without paddle
        # installed — the ImportError surfaces only on first use, giving the
        # caller a clean path to detect the missing dep.
        try:
            from paddleocr import PaddleOCR  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "PaddleOCR is not installed. "
                "Install it with: pip install 'paddleocr>=2.7,<3' 'paddlepaddle>=2.6,<3'. "
                "Alternatively, set ALV_OCR_PROVIDER=stub to use the deterministic stub."
            ) from exc

        _paddle_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _paddle_instance


class PaddleOcrProvider(OcrProvider):
    """Real PaddleOCR provider.

    Implements the ``OcrProvider`` interface so the pipeline layer is unaware
    of the underlying library. Model weights are loaded once and reused across
    all requests (lazy singleton via ``_get_paddle()``).

    Input: raw PNG/JPEG bytes (typically the preprocessed image from the
    preprocess stage).
    Output: a tuple of ``OcrToken`` objects, one per detected text line.
    """

    name = "paddle"

    def extract(self, image_bytes: bytes) -> Sequence[OcrToken]:
        """Run PaddleOCR on ``image_bytes`` and return a token sequence.

        Args:
            image_bytes: PNG or JPEG image bytes.

        Returns:
            A (possibly empty) tuple of ``OcrToken`` values.

        Raises:
            ValueError: if the image cannot be decoded from ``image_bytes``.
        """
        # ----------------------------------------------------------------
        # Decode bytes → numpy array
        # ----------------------------------------------------------------
        if not image_bytes:
            raise ValueError("Image could not be decoded")
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Image could not be decoded")

        # ----------------------------------------------------------------
        # Run PaddleOCR
        # ----------------------------------------------------------------
        paddle = _get_paddle()
        result = paddle.ocr(img, cls=True)  # type: ignore[union-attr]

        # ----------------------------------------------------------------
        # Normalise the result into OcrToken objects
        # ----------------------------------------------------------------
        # PaddleOCR may return None or a nested list.  The outer list has one
        # element per page (we always pass a single image); the inner list
        # contains one entry per detected line: [[quad_points], (text, score)].
        if not result:
            return ()

        # Flatten page wrapper if present (PaddleOCR >= 2.6 wraps in a list)
        page = result[0] if isinstance(result[0], list) else result
        if not page:
            return ()

        tokens: list[OcrToken] = []
        for line in page:
            if not line:
                continue
            quad, (text, confidence) = line
            # quad is a list of 4 [x, y] points (float).
            # Convert to axis-aligned bounding box via min/max.
            xs = [round(pt[0]) for pt in quad]
            ys = [round(pt[1]) for pt in quad]
            bbox = BoundingBox(
                x0=max(0, min(xs)),
                y0=max(0, min(ys)),
                x1=max(0, max(xs)),
                y1=max(0, max(ys)),
            )
            tokens.append(
                OcrToken(
                    text=str(text),  # raw — never mutated per AGENTS.md
                    bbox=bbox,
                    confidence=float(confidence),
                )
            )
        return tuple(tokens)
