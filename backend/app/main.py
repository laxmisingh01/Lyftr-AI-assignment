"""
app/main.py
───────────
FastAPI application factory.

Startup sequence:
  1. Initialise SQLite database (creates tables if absent).
  2. Initialise LiteLLM in-memory cache (if CACHE_ENABLED=true).
  3. Register routers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    import litellm
except ImportError:
    litellm = None

from app.config import settings
from app.database import init_db
from app.routes import router


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    print("[startup] Initialising database …")
    init_db()

    if litellm is not None and settings.cache_enabled:
        print("[startup] Enabling LiteLLM in-memory cache …")
        # LiteLLM 1.110 uses "local" for its process-local in-memory cache.
        litellm.cache = litellm.Cache(type="local")
        litellm.cache_responses = True
    elif litellm is not None:
        litellm.cache = None
        litellm.cache_responses = False

    keys = settings.parse_api_keys()
    print(f"[startup] {len(keys)} API key(s) configured: {list(keys.keys())}")
    print("[startup] Ready.")

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────
    print("[shutdown] Goodbye.")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Lyftr AI",
    description="LLM chat API with multi-key failover and response caching.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parse_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
