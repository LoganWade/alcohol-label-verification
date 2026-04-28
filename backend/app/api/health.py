"""Liveness/readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.settings import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    ocr_provider: str
    ocr_model_loaded: bool


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    # Phase 1: the stub provider is always loaded. Phase 2 will set this to
    # False until the PaddleOCR model finishes initializing on first use.
    return HealthResponse(
        status="ok",
        version=__version__,
        ocr_provider=settings.ocr_provider,
        ocr_model_loaded=True,
    )
