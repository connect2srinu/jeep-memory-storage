"""Serve the ADK dev UI with short-term sessions in Postgres and long-term memory in Memory Bank.

ADK's `adk web` CLI registers the Postgres session factory under the bare ``postgresql`` scheme,
but ``DatabaseSessionService`` requires an async driver URL (``postgresql+asyncpg://``) whose URL
scheme the CLI does not recognize. This launcher registers that async scheme on ADK's (singleton)
service registry and then builds the standard ADK dev-UI app, so short-term sessions land in
Postgres and long-term memory in Vertex AI Memory Bank.

Run (same env as the demo):

    python -m memory_agent.serve

Then open http://localhost:8000/dev-ui/?app=memory_agent
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.cli.service_registry import get_service_registry
from google.adk.sessions.database_session_service import DatabaseSessionService

from .settings import settings

# The directory that contains the ``memory_agent`` agent package (ADK discovers apps here).
AGENTS_DIR = str(Path(__file__).resolve().parent.parent)


def _async_postgres_session(uri: str, **kwargs: Any) -> DatabaseSessionService:
    kwargs.pop("agents_dir", None)
    return DatabaseSessionService(db_url=uri)


def build_app():
    if not settings.agent_engine_id:
        raise ValueError("AGENT_PLATFORM_MEMORY_BANK_ID is required for Memory Bank")
    get_service_registry().register_session_service("postgresql+asyncpg", _async_postgres_session)
    return get_fast_api_app(
        agents_dir=AGENTS_DIR,
        session_service_uri=settings.sessions_database_url,
        memory_service_uri=f"agentengine://{settings.agent_engine_id}",
        web=True,
    )


def main() -> None:
    uvicorn.run(
        build_app(),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
