"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import health, reviews, samples
from app.core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Prototype API for AI-powered alcohol label verification. "
            "Returns deterministic, evidence-backed comparisons; never "
            "issues approve/reject decisions."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # API routers MUST be registered before the static file mount so the
    # catch-all StaticFiles handler does not shadow /api/* routes.
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(reviews.router, prefix=settings.api_v1_prefix)
    app.include_router(samples.router, prefix=settings.api_v1_prefix)

    # Production: serve the built React frontend as static files.
    #
    # StaticFiles with html=True handles /, /index.html, and any direct asset
    # paths (e.g. /assets/index-abc123.js).  It does NOT fall back to
    # index.html for deep client-side routes like /review/new, so we add an
    # explicit catch-all GET route below that returns index.html for any path
    # not already matched — this is the standard SPA pattern on Starlette.
    #
    # Mount order matters: the StaticFiles sub-application is mounted AFTER
    # all routers so /api/v1/* is always preferred.
    if settings.static_dir is not None:
        static_index = Path(settings.static_dir) / "index.html"

        # Serve real static assets (JS, CSS, images, etc.)
        app.mount(
            "/assets",
            StaticFiles(directory=Path(settings.static_dir) / "assets"),
            name="frontend-assets",
        )

        # Explicit root route
        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(static_index)

        # SPA catch-all: any GET path not matched above returns index.html so
        # React Router can handle client-side navigation.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            # If the requested path is a real file (e.g. favicon.ico, robots.txt)
            # serve it directly; otherwise fall back to index.html.
            candidate = Path(settings.static_dir) / full_path  # type: ignore[arg-type]
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_index)

    return app


app = create_app()
