"""
app/models.py
─────────────
Pydantic request / response schemas.
These match the assignment API contract exactly — do not rename fields.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


# ── GET /health ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str                 # always "ok"
    keys_configured: int        # number of valid API keys loaded
    cache_enabled: bool         # reflects CACHE_ENABLED setting


# ── POST /chat ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    system_prompt: Optional[str] = None


class ChatMetadata(BaseModel):
    resolution_source: str      # "LIVE_INFERENCE" | "LLM_CACHE"
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]       # None on cache hit
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata


# ── GET /sessions/{session_id}/messages ──────────────────────────────────────

class MessageItem(BaseModel):
    role: str
    content: str
    metadata: Optional[dict] = None     # only present on assistant messages


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[MessageItem]
