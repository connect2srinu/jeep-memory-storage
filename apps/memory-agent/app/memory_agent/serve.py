"""Serve the ADK dev UI with short-term sessions in Postgres (long-term is the Control Plane).

ADK's `adk web` CLI registers the Postgres session factory under the bare ``postgresql`` scheme,
but ``DatabaseSessionService`` requires an async driver URL (``postgresql+asyncpg://``) whose URL
scheme the CLI does not recognize. This launcher registers that async scheme on ADK's (singleton)
service registry and then builds the standard ADK dev-UI app, so short-term sessions land in
Postgres. Long-term memory is the governed preference profile reached through the runtime API from
the agent's callbacks, so no ADK memory service is wired here.

Run (same env as the demo):

    python -m memory_agent.serve

Then open http://localhost:8000/dev-ui/?app=memory_agent
"""

from __future__ import annotations

import logging
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
    get_service_registry().register_session_service("postgresql+asyncpg", _async_postgres_session)
    return get_fast_api_app(
        agents_dir=AGENTS_DIR,
        session_service_uri=settings.sessions_database_url,
        web=True,
    )


def main() -> None:
    # Show the agent's memory-decision events (INFO) next to uvicorn's own output.
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s %(message)s"
    )
    uvicorn.run(
        build_app(),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
