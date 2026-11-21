"""
app/database.py
───────────────
SQLite connection management and schema initialisation.

Design decisions:
- Uses stdlib sqlite3 only (no ORM) to keep the dependency list minimal.
- WAL journal mode prevents read/write contention in Docker.
- Schema is created idempotently at startup via CREATE TABLE IF NOT EXISTS.
- sessions  → stores session_id + optional system_prompt
- messages  → stores the full conversation turn history
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List, Optional

from app.config import settings


# ── Resolve the DB file path ───────────────────────────────────────────────────

def _resolve_db_path() -> str:
    path = settings.sqlite_path()
    # Handle relative paths relative to the backend working directory
    if not os.path.isabs(path):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, path)
    return path


DB_PATH: str = _resolve_db_path()


# ── Schema DDL ────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    system_prompt TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    role         TEXT    NOT NULL,       -- 'user' | 'assistant'
    content      TEXT    NOT NULL,
    metadata     TEXT,                   -- JSON blob (assistant turns only)
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
"""


# ── Initialisation ────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the data directory (if needed) and apply the schema."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_DDL)
    print(f"[db] Initialised database at {DB_PATH}")


def check_db() -> bool:
    """
    Quick connectivity probe used by GET /health.
    Returns True if the DB is reachable and both tables exist.
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=3) as conn:
            conn.execute("SELECT 1")
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        return {"sessions", "messages"}.issubset(tables)
    except Exception:
        return False


# ── Connection context manager ────────────────────────────────────────────────

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a sqlite3 connection with row_factory set to Row."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Session helpers ───────────────────────────────────────────────────────────

def upsert_session(session_id: str, system_prompt: Optional[str] = None) -> None:
    """
    Create a session row if it doesn't exist.
    If system_prompt is provided, overwrite the stored value.
    """
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT session_id, system_prompt FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if existing is None:
            conn.execute(
                "INSERT INTO sessions (session_id, system_prompt, created_at) VALUES (?, ?, ?)",
                (session_id, system_prompt, now),
            )
        elif system_prompt is not None:
            conn.execute(
                "UPDATE sessions SET system_prompt = ? WHERE session_id = ?",
                (system_prompt, session_id),
            )


def get_session(session_id: str) -> Optional[sqlite3.Row]:
    """Return the sessions row or None."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()


def get_session_system_prompt(session_id: str) -> Optional[str]:
    """Return just the system prompt for a session, or None."""
    row = get_session(session_id)
    if row is None:
        return None
    return row["system_prompt"]


# ── Message helpers ───────────────────────────────────────────────────────────

def insert_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """Append one message to the messages table."""
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO messages (session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, meta_json, now),
        )


def save_chat_turn(
    session_id: str,
    system_prompt: Optional[str],
    user_content: str,
    assistant_content: str,
    metadata: dict,
) -> None:
    """Persist a successful session update and both messages atomically."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO sessions (session_id, system_prompt, created_at) VALUES (?, ?, ?)",
                (session_id, system_prompt, now),
            )
        elif system_prompt is not None:
            conn.execute(
                "UPDATE sessions SET system_prompt = ? WHERE session_id = ?",
                (system_prompt, session_id),
            )
        conn.executemany(
            """
            INSERT INTO messages (session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (session_id, "user", user_content, None, now),
                (session_id, "assistant", assistant_content, json.dumps(metadata), now),
            ],
        )


def get_messages(session_id: str) -> List[dict]:
    """
    Return all messages for a session in insertion order.
    Assistant messages include their metadata dict.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT role, content, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    result = []
    for row in rows:
        entry: dict = {"role": row["role"], "content": row["content"]}
        if row["role"] == "assistant" and row["metadata"]:
            entry["metadata"] = json.loads(row["metadata"])
        result.append(entry)
    return result
