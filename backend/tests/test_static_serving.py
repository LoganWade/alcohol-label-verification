"""Tests for static file serving in production mode.

Verifies that:
- API routes are not shadowed by the StaticFiles catch-all.
- The React index.html is served at / and for unknown SPA routes.
- Without ALV_STATIC_DIR set, / returns 404 (no static serving in dev mode).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

INDEX_HTML = "<html><body><h1>Test App</h1></body></html>"


@pytest.fixture()
def static_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a minimal index.html and assets/."""
    (tmp_path / "index.html").write_text(INDEX_HTML)
    # The /assets StaticFiles mount requires the directory to exist.
    (tmp_path / "assets").mkdir()
    return tmp_path


@pytest.fixture()
def client_with_static(static_dir: Path) -> TestClient:
    """TestClient for an app instance with ALV_STATIC_DIR configured."""
    # Import here so the module-level `settings` singleton is not yet imported.
    # We manipulate the env var before instantiating create_app() so the
    # Settings() call inside create_app() picks it up fresh.
    os.environ["ALV_STATIC_DIR"] = str(static_dir)
    try:
        # Re-import create_app fresh each time so settings re-reads env.
        import importlib

        import app.core.settings as settings_mod
        import app.main as main_mod

        importlib.reload(settings_mod)
        importlib.reload(main_mod)

        from app.main import create_app

        application = create_app()
        return TestClient(application, raise_server_exceptions=True)
    finally:
        os.environ.pop("ALV_STATIC_DIR", None)


@pytest.fixture()
def client_without_static() -> TestClient:
    """TestClient for an app instance WITHOUT ALV_STATIC_DIR (dev mode)."""
    os.environ.pop("ALV_STATIC_DIR", None)

    import importlib

    import app.core.settings as settings_mod
    import app.main as main_mod

    importlib.reload(settings_mod)
    importlib.reload(main_mod)

    from app.main import create_app

    application = create_app()
    return TestClient(application, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# With static dir set
# ---------------------------------------------------------------------------


def test_health_not_swallowed_by_static(client_with_static: TestClient) -> None:
    """GET /api/v1/health must still return 200 when static files are mounted."""
    response = client_with_static.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_root_serves_index_html(client_with_static: TestClient) -> None:
    """GET / returns 200 with the contents of index.html."""
    response = client_with_static.get("/")
    assert response.status_code == 200
    assert "Test App" in response.text


def test_spa_fallback_for_unknown_route(client_with_static: TestClient) -> None:
    """GET /some/random/route returns index.html (SPA client-side routing fallback)."""
    response = client_with_static.get("/some/random/route")
    assert response.status_code == 200
    assert "Test App" in response.text


def test_path_traversal_does_not_leak_files(client_with_static: TestClient) -> None:
    """Catch-all must never serve files outside the static dir.

    Even when a normalized path resolves to a real file on disk (e.g.
    /etc/hostname), the SPA handler should fall back to index.html. We don't
    do any path resolution in the handler; this test guards against future
    regressions that reintroduce manual file resolution.
    """
    # Starlette normalizes /../ in the URL path before routing, so this
    # request is effectively GET /etc/hostname after normalization.
    response = client_with_static.get("/../../../../etc/hostname")
    assert response.status_code == 200
    # The response body must be index.html, NOT the contents of /etc/hostname.
    assert "Test App" in response.text


# ---------------------------------------------------------------------------
# Without static dir (dev mode)
# ---------------------------------------------------------------------------


def test_root_404_without_static_dir(client_without_static: TestClient) -> None:
    """In dev mode (no ALV_STATIC_DIR), GET / should 404 — no static serving."""
    response = client_without_static.get("/")
    assert response.status_code == 404


def test_health_works_without_static_dir(client_without_static: TestClient) -> None:
    """Health endpoint works in dev mode regardless of static dir."""
    response = client_without_static.get("/api/v1/health")
    assert response.status_code == 200
