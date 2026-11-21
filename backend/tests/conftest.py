"""
tests/conftest.py
─────────────────
Shared pytest fixtures.

Uses an isolated in-memory/temp SQLite database so tests never
touch the real database file.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def test_env(tmp_path_factory):
    """
    Point DATABASE_URL at a temporary file for the whole test session.
    Set minimal env vars so Settings loads cleanly without a real .env file.
    """
    db_file = tmp_path_factory.mktemp("data") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    os.environ["LLM_API_KEYS"] = "key_1=test-key-1,key_2=test-key-2"
    os.environ["LLM_MODEL"] = "gpt-4o-mini"
    os.environ["CACHE_ENABLED"] = "true"
    os.environ["ENABLE_FAILURE_SIMULATION"] = "false"
    yield
    # cleanup is automatic (tmp_path_factory)


@pytest.fixture(scope="session")
def client(test_env):
    """Return a TestClient for the FastAPI app."""
    # Import after env vars are set
    from app.main import app
    with TestClient(app) as c:
        yield c
