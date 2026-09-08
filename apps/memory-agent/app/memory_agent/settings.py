from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True, slots=True)
class MemoryAgentSettings:
    # Long-term memory: Vertex AI Memory Bank (the existing Agent Engine / reasoning engine).
    project: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    agent_engine_id: str | None = (
        os.getenv("AGENT_PLATFORM_MEMORY_BANK_ID") or os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    )
    # Short-term memory: ADK sessions persisted in Cloud SQL / PostgreSQL. ADK v2's
    # DatabaseSessionService uses an async SQLAlchemy engine, so an asyncpg URL is expected;
    # it defaults to the same Postgres the control plane uses.
    sessions_database_url: str = os.getenv(
        "SESSIONS_DATABASE_URL",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://shared_memory:local-development-only@localhost:5432/shared_memory",
        ),
    )
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    app_name: str = os.getenv("ADK_APP_NAME", "dual_memory_agent")


settings = MemoryAgentSettings()
