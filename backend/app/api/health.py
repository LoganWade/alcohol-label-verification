"""Liveness/readiness endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.settings import settings

router = APIRouter()

# Sentinel file written by the Dockerfile model-preload step when the
# preload fails (network unavailable, registry blocked, etc.). When present,
# the deploy is still up but the first analyze call will pay the cold-start
# cost (≈200 MB download + ~3 s model init), blowing past the 5 s budget.
# Surface this in /health so reviewers can see the degraded state immediately
# instead of finding out the hard way mid-demo.
#
# Path is taken from settings.paddle_preload_sentinel_path so the Dockerfile
# location and the runtime check stay in sync via a single configurable knob
# rather than two separately-hardcoded paths.
_PADDLE_PRELOAD_FAILED_SENTINEL = Path(settings.paddle_preload_sentinel_path)


class HealthResponse(BaseModel):
    status: str
    version: str
    ocr_provider: str
    ocr_model_loaded: bool
    paddle_preload_failed: bool = False


def _ocr_model_loaded() -> bool:
    """Report real readiness for the configured OCR provider.

    Stub: always True (no model to load).
    Paddle: True only after the lazy singleton has been initialised —
    typically after the build-time preload + first warmup ping.
    """
    if settings.ocr_provider == "paddle":
        # Import deferred so importing health.py doesn't pull in paddle.
        from app.services.extraction.paddle_ocr import is_paddle_loaded

        return is_paddle_loaded()
    return True


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        ocr_provider=settings.ocr_provider,
        ocr_model_loaded=_ocr_model_loaded(),
        paddle_preload_failed=_PADDLE_PRELOAD_FAILED_SENTINEL.exists(),
    )
