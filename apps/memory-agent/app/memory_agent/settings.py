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
    # Short-term memory: ADK sessions persisted in Cloud SQL / PostgreSQL. ADK v2's
    # DatabaseSessionService uses an async SQLAlchemy engine, so an asyncpg URL is expected.
    sessions_database_url: str = os.getenv(
        "SESSIONS_DATABASE_URL",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://shared_memory:local-development-only@localhost:5432/shared_memory",
        ),
    )
    # Long-term memory: governed structured preferences via the Control Plane runtime API.
    control_plane_api_url: str = os.getenv("CONTROL_PLANE_API_URL", "http://localhost:8080")
    control_plane_api_token: str | None = os.getenv("CONTROL_PLANE_API_TOKEN")
    control_plane_api_audience: str | None = os.getenv("CONTROL_PLANE_API_AUDIENCE")
    agent_id: str = os.getenv("REFERENCE_AGENT_ID", "grocery-agent")
    consumer_domain: str = os.getenv("PREFERENCE_DOMAIN", "grocery")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    app_name: str = os.getenv("ADK_APP_NAME", "dual_memory_agent")


settings = MemoryAgentSettings()
