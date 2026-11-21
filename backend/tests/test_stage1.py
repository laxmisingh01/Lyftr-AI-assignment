"""
tests/test_stage1.py
────────────────────
Stage 1 tests:
  - GET /health response shape and values
  - Database initialisation (tables exist)
  - Session system-prompt persistence
  - GET /sessions/{id}/messages (empty, 404, hidden system prompt)
"""

import json
import pytest


# ── Health endpoint ───────────────────────────────────────────────────────────

class TestHealth:
    def test_status_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_exact_shape(self, client):
        body = client.get("/health").json()
        assert set(body.keys()) == {"status", "keys_configured", "cache_enabled"}

    def test_status_value(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"

    def test_keys_configured(self, client):
        body = client.get("/health").json()
        # conftest sets two keys
        assert body["keys_configured"] == 2

    def test_cache_enabled(self, client):
        body = client.get("/health").json()
        # CACHE_ENABLED=true in conftest
        assert body["cache_enabled"] is True


# ── Database ──────────────────────────────────────────────────────────────────

class TestDatabase:
    def test_check_db_passes(self):
        from app.database import check_db
        assert check_db() is True

    def test_sessions_table_exists(self):
        import sqlite3
        from app.database import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "sessions" in tables

    def test_messages_table_exists(self):
        import sqlite3
        from app.database import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "messages" in tables


# ── Session system-prompt persistence ─────────────────────────────────────────

class TestSessionPersistence:
    def test_upsert_creates_session(self):
        from app.database import upsert_session, get_session
        upsert_session("sess-test-001", system_prompt="You are helpful.")
        row = get_session("sess-test-001")
        assert row is not None
        assert row["session_id"] == "sess-test-001"
        assert row["system_prompt"] == "You are helpful."

    def test_upsert_updates_system_prompt(self):
        from app.database import upsert_session, get_session_system_prompt
        upsert_session("sess-test-002", system_prompt="First prompt")
        upsert_session("sess-test-002", system_prompt="Updated prompt")
        sp = get_session_system_prompt("sess-test-002")
        assert sp == "Updated prompt"

    def test_session_without_prompt(self):
        from app.database import upsert_session, get_session_system_prompt
        upsert_session("sess-test-003")
        sp = get_session_system_prompt("sess-test-003")
        assert sp is None

    def test_unknown_session_returns_none(self):
        from app.database import get_session
        assert get_session("nonexistent-session-xyz") is None


# ── Sessions messages endpoint ────────────────────────────────────────────────

class TestSessionMessages:
    def test_404_for_unknown_session(self, client):
        r = client.get("/sessions/does-not-exist/messages")
        assert r.status_code == 404
        assert r.json()["detail"] == "session not found"

    def test_empty_message_list_for_new_session(self):
        from app.database import upsert_session, get_messages
        upsert_session("sess-empty-001")
        msgs = get_messages("sess-empty-001")
        assert msgs == []

    def test_system_prompt_not_in_messages_endpoint(self, client):
        from app.database import upsert_session
        upsert_session("sess-hidden-sp", system_prompt="SECRET PROMPT")
        r = client.get("/sessions/sess-hidden-sp/messages")
        assert r.status_code == 200
        body = r.json()
        # System prompt must NOT appear in the messages list
        for msg in body["messages"]:
            assert msg["role"] != "system"
            assert "SECRET PROMPT" not in msg["content"]

    def test_response_shape(self, client):
        from app.database import upsert_session
        upsert_session("sess-shape-check")
        r = client.get("/sessions/sess-shape-check/messages")
        assert r.status_code == 200
        body = r.json()
        assert "session_id" in body
        assert "messages" in body
        assert isinstance(body["messages"], list)
