"""
app/routes.py
─────────────
FastAPI route definitions for health, chat, and persisted session history.
"""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Header, HTTPException

try:
    import litellm
except ImportError:
    litellm = None

from app.config import settings
from app.database import check_db, get_session, get_messages, save_chat_turn
from app.llm_gateway import AllProvidersUnavailable, complete, parse_simulation_header
from app.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MessageItem,
    SessionMessagesResponse,
)

router = APIRouter()

RESPONSE_STYLE_PROMPT = (
    "Keep replies concise but complete. Answer simple questions in a few sentences; "
    "use short sections or bullets when a question needs multiple steps. Include the "
    "full explanation or requested steps, and never stop mid-sentence. Avoid headings "
    "for simple answers; use Markdown formatting only when it improves readability. "
    "Expand when the user explicitly asks for detail."
)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    simulate_failure: str | None = Header(default=None, alias="X-Simulate-Failure"),
) -> ChatResponse:
    started = perf_counter()

    existing_session = get_session(request.session_id)
    stored_prompt = existing_session["system_prompt"] if existing_session else None
    effective_prompt = (
        request.system_prompt if request.system_prompt is not None else stored_prompt
    )

    simulation: dict[str, int] = {}
    if settings.enable_failure_simulation and simulate_failure is not None:
        try:
            simulation = parse_simulation_header(simulate_failure)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    history = get_messages(request.session_id) if existing_session else []

    messages: list[dict[str, str]] = []
    if effective_prompt:
        system_content = f"{effective_prompt}\n\n{RESPONSE_STYLE_PROMPT}"
    else:
        system_content = RESPONSE_STYLE_PROMPT
    messages.append({"role": "system", "content": system_content})
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item["role"] in {"user", "assistant"}
    )
    messages.append({"role": "user", "content": request.message})

    try:
        result = await complete(messages, simulated_failures=simulation)
    except AllProvidersUnavailable as exc:
        raise HTTPException(status_code=503, detail="all providers unavailable") from exc

    latency_ms = int((perf_counter() - started) * 1000)
    resolution_source = "LLM_CACHE" if result.cache_hit else "LIVE_INFERENCE"
    response_metadata = {
        "resolution_source": resolution_source,
        "model": result.model,
        "latency_ms": latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "key_id": None if result.cache_hit else result.key_id,
        "fallback_attempts": 0 if result.cache_hit else result.fallback_attempts,
    }
    persisted_metadata = {
        "resolution_source": resolution_source,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }
    save_chat_turn(
        session_id=request.session_id,
        system_prompt=effective_prompt,
        user_content=request.message,
        assistant_content=result.reply,
        metadata=persisted_metadata,
    )
    return ChatResponse(
        session_id=request.session_id,
        reply=result.reply,
        metadata=response_metadata,
    )


# ── GET /health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """
    Returns service health.
    Checks:
      1. Database connectivity + table presence.
      2. Number of configured API keys.
      3. Whether cache is active.
    """
    if not check_db():
        raise HTTPException(status_code=503, detail="database unavailable")

    keys = settings.parse_api_keys()
    if litellm is not None:
        cache_active = settings.cache_enabled and litellm.cache is not None
    else:
        cache_active = settings.cache_enabled

    return HealthResponse(
        status="ok",
        keys_configured=len(keys),
        cache_enabled=cache_active,
    )


# ── GET /sessions/{session_id}/messages ──────────────────────────────────────

@router.get(
    "/sessions/{session_id}/messages",
    response_model=SessionMessagesResponse,
)
def session_messages(session_id: str) -> SessionMessagesResponse:
    """
    Returns the message history for a session.
    - 404 if the session_id is unknown.
    - System prompt is NOT included in the response (stored separately).
    """
    row = get_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")

    raw = get_messages(session_id)
    messages = [MessageItem(**m) for m in raw]

    return SessionMessagesResponse(session_id=session_id, messages=messages)
