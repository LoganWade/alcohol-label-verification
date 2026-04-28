"""OCR provider interface and the Phase 1 stub implementation.

The interface (``OcrProvider``) is the swap-point between the prototype's
deterministic stub provider and the real local PaddleOCR provider that lands
in Phase 2. Downstream stages see only the typed token list and never touch
provider-specific code.

Per AGENTS.md:
- The raw token text from the provider is **immutable evidence**. Stages that
  want to compare or normalize must operate on copies.
- Confidence values flow forward unchanged; uncertainty propagates rather
  than getting smoothed away.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.schemas.common import BoundingBox, OcrToken


class OcrProvider(ABC):
    """Strategy interface for OCR providers.

    Implementations must be self-contained and side-effect-free with respect
    to their inputs (the image bytes). They must not log, write to disk, or
    make network calls in a way that changes between runs on the same input.
    """

    name: str

    @abstractmethod
    def extract(self, image_bytes: bytes) -> Sequence[OcrToken]:
        """Run OCR on the given image bytes and return tokens."""


class StubOcrProvider(OcrProvider):
    """Deterministic Phase 1 stub.

    Emits a fixed token list regardless of input. Its sole purpose is to keep
    the pipeline wired end-to-end so the analyze endpoint, schema validation,
    and the frontend integration can be developed against a real contract
    before the Phase 2 PaddleOCR provider lands.

    The token coordinates are placeholders and will not align with any real
    image; the frontend treats missing or out-of-bounds bboxes gracefully.
    """

    name = "stub"

    _TOKENS: tuple[OcrToken, ...] = (
        OcrToken(
            text="OLD TOM DISTILLERY",
            bbox=BoundingBox(x0=120, y0=80, x1=540, y1=140),
            confidence=0.94,
        ),
        OcrToken(
            text="Kentucky Straight Bourbon Whiskey",
            bbox=BoundingBox(x0=110, y0=160, x1=560, y1=200),
            confidence=0.91,
        ),
        OcrToken(
            text="45% Alc./Vol.",
            bbox=BoundingBox(x0=240, y0=240, x1=420, y1=280),
            confidence=0.96,
        ),
        OcrToken(
            text="750 mL",
            bbox=BoundingBox(x0=280, y0=300, x1=380, y1=340),
            confidence=0.97,
        ),
        OcrToken(
            text="Bottled by Old Tom Co., Frankfort, KY",
            bbox=BoundingBox(x0=80, y0=380, x1=580, y1=420),
            confidence=0.88,
        ),
        OcrToken(
            text=(
                "GOVERNMENT WARNING: (1) According to the Surgeon General, "
                "women should not drink alcoholic beverages during pregnancy "
                "because of the risk of birth defects. (2) Consumption of "
                "alcoholic beverages impairs your ability to drive a car or "
                "operate machinery, and may cause health problems."
            ),
            bbox=BoundingBox(x0=60, y0=520, x1=620, y1=720),
            confidence=0.82,
        ),
    )

    def extract(self, image_bytes: bytes) -> Sequence[OcrToken]:
        # image_bytes is intentionally ignored in the stub. The signature
        # matches the real provider so the call site remains identical.
        return self._TOKENS


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------
def get_ocr_provider(name: str) -> OcrProvider:
    """Return an OCR provider by name.

    Registered providers:
    - ``"stub"``   — deterministic Phase 1 stub; always available; no heavy deps.
    - ``"paddle"`` — real PaddleOCR provider added in Phase 2; requires
      ``paddleocr`` and ``paddlepaddle`` to be installed.

    Unknown names raise ``ValueError`` so config errors fail loudly at startup
    rather than producing surprising behaviour at request time.
    """

    if name == "stub":
        return StubOcrProvider()
    if name == "paddle":
        from app.services.extraction.paddle_ocr import PaddleOcrProvider

        return PaddleOcrProvider()
    raise ValueError(
        f"Unknown OCR provider: {name!r}. Supported providers: 'stub', 'paddle'."
    )
