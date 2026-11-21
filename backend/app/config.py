"""
app/config.py
─────────────
Loads all runtime configuration from environment variables / .env file.
No secrets are hard-coded here.
"""

from __future__ import annotations

import os
from typing import Dict, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────
    # Raw string: "key_1=sk-abc,key_2=sk-xyz"
    llm_api_keys: str = ""
    # Optional provider-specific variables. These are convenient when secrets
    # are stored separately in a Render Environment Group.
    openai: str = ""
    gemini: str = ""
    llm_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.5-flash"
    llm_max_output_tokens: int = 2048

    # Comma-separated browser origins allowed to call the API.
    allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # ── Database ───────────────────────────────────────────────
    # e.g. "sqlite:///./data/app.db"
    database_url: str = "sqlite:///./data/app.db"

    # ── Cache ──────────────────────────────────────────────────
    cache_enabled: bool = True

    # ── Failure simulation ─────────────────────────────────────
    enable_failure_simulation: bool = False

    # ── Derived helpers ────────────────────────────────────────
    def parse_api_keys(self) -> Dict[str, str]:
        """
        Parse LLM_API_KEYS and optional provider-specific variables into an ordered dict.
        Input : "key_1=sk-abc,key_2=sk-xyz"
        Output: {"key_1": "sk-abc", "key_2": "sk-xyz"}
        OPENAI and GEMINI are appended as fallbacks when provided separately.
        Order is preserved (Python 3.7+).
        """
        result: Dict[str, str] = {}
        if self.llm_api_keys.strip():
            for pair in self.llm_api_keys.split(","):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    result[k.strip()] = v.strip()
        for provider in ("openai", "gemini"):
            value = getattr(self, provider).strip()
            if value and provider not in result:
                result[provider] = value
        return result

    def parse_allowed_origins(self) -> List[str]:
        """Parse comma-separated CORS origins from ALLOWED_ORIGINS."""
        return [origin.strip().rstrip("/") for origin in self.allowed_origins.split(",") if origin.strip()]

    def sqlite_path(self) -> str:
        """
        Extract the filesystem path from DATABASE_URL.
        Strips the 'sqlite:///' prefix.
        """
        url = self.database_url
        for prefix in ("sqlite:///", "sqlite://"):
            if url.startswith(prefix):
                return url[len(prefix):]
        return url


# Module-level singleton — import this everywhere.
settings = Settings()
