"""
Shared test fixtures and dependency overrides.

Key responsibilities:
  1. Override `get_db` so tests never hit the real PostgreSQL database.
     A MagicMock session is returned; individual tests mock CRUD functions
     at the correct import path (where they are USED, not where defined).
  2. Reset the in-memory rate-limit window between every test so counter
     state from one test does not bleed into the next.
  3. Suppress the real DB connection during lifespan startup.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── DB override ───────────────────────────────────────────────────────────────

async def _mock_db_session():
    """Yield a no-op async DB session. Real DB never contacted."""
    session = AsyncMock()
    yield session


# ── Rate-limit reset ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_rate_limit_windows():
    """Clear in-memory rate-limit counters before each test."""
    from app.middleware.rate_limit import _windows
    _windows.clear()
    yield
    _windows.clear()


# ── App client with DB override + suppressed lifespan DB call ─────────────────

@pytest.fixture
def client():
    from app.main import app
    from app.database import get_db

    app.dependency_overrides[get_db] = _mock_db_session

    # Suppress the real `Base.metadata.create_all` on startup
    with patch("app.main.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value = mock_conn
        mock_engine.connect.return_value = mock_conn
        mock_engine.dispose = AsyncMock()

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.clear()
