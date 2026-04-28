"""Runtime settings loaded from environment with safe defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ALV_",
        case_sensitive=False,
        extra="ignore",
    )

    # API
    app_name: str = "Alcohol Label Verification"
    api_v1_prefix: str = "/api/v1"

    # Uploads
    max_upload_bytes: int = Field(default=10 * 1024 * 1024)  # 10 MB
    # Note: application/pdf is intentionally NOT supported. The preprocess
    # stage uses Pillow only and does not rasterize PDFs. PDF support is
    # tracked in docs/roadmap.md as a future enhancement.
    allowed_image_types: tuple[str, ...] = ("image/png", "image/jpeg")

    # OCR provider selection. Phase 1 ships only the stub provider; Phase 2
    # adds "paddle" and registers it via the provider factory.
    ocr_provider: str = "stub"

    # Sample data directory (synthetic + TTB reference labels for demo mode).
    # Resolved relative to the repo root at runtime; override with
    # ALV_SAMPLES_DIR for production deployments.
    samples_dir: str = str(
        Path(__file__).resolve().parent.parent.parent.parent / "sample_data"
    )

    # CORS for local frontend dev. Tightened in deployment.
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    )

    # Static files directory for serving the built React frontend.
    # When set, FastAPI mounts the directory at "/" with html=True so
    # React Router client-side routes work correctly.
    # Defaults to None (dev mode — frontend runs separately on Vite).
    # Set ALV_STATIC_DIR=/home/user/app/frontend_dist in production.
    static_dir: str | None = None


settings = Settings()
