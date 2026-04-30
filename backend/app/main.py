"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import batches, health, reviews, samples
from app.core.settings import settings
from app.services.batch.storage import get_store


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Initialize the batch SQLite store (creates the DB file on first run
    # and applies any pending migrations). Idempotent; safe on every
    # startup. Doing this in the lifespan handler means the first
    # request never pays the migration cost or sees a missing-table error.
    get_store()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Prototype API for AI-powered alcohol label verification. "
            "Returns deterministic, evidence-backed comparisons; never "
            "issues approve/reject decisions."
        ),
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

    # API routers MUST be registered before the static file mount so the
    # catch-all StaticFiles handler does not shadow /api/* routes.
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(reviews.router, prefix=settings.api_v1_prefix)
    app.include_router(samples.router, prefix=settings.api_v1_prefix)
    app.include_router(batches.router, prefix=settings.api_v1_prefix)

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
        #
        # Real static assets (JS/CSS/images) are served by the /assets mount
        # above. We deliberately do NOT resolve `full_path` against the static
        # directory here: doing so requires careful path-traversal hardening
        # (segments like `..` normalize via Path.resolve()) and we ship no
        # root-level static files that would benefit from it. Returning
        # index.html for every unmatched route keeps the surface minimal.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            # full_path is consumed by the route matcher; the value isn't used
            # in the body since we always return index.html.
            del full_path
            return FileResponse(static_index)

    return app


app = create_app()
