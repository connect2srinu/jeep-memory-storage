"""ADK agent with split memory: short-term in Postgres, long-term as governed preferences.

Short-term (session/conversation) state is persisted by ADK's ``DatabaseSessionService`` into
Cloud SQL / PostgreSQL. Long-term memory is NOT ADK Memory Bank here: it is the Control Plane's
structured, governed preference profiles (e.g. ``{domain}-preferences-v1`` schemas). The agent
resolves the effective preference snapshot for the Session before the model runs and writes new
preferences back through the runtime API, so long-term memory always lands in the defined schemas.
"""

from __future__ import annotations

import json
from typing import Any

from google.adk import Runner
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini, LlmRequest
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import ToolContext

from .client import (
    ControlPlaneApiClient,
    GoogleIdTokenProvider,
    StaticTokenProvider,
)
from .settings import settings

SNAPSHOT_STATE_KEY = "shared_memory:effective_snapshot"

INSTRUCTION = f"""
You are a helpful assistant for the {settings.consumer_domain} domain with two kinds of memory.

Short-term memory is the current conversation (this Session). Long-term memory is the user's
governed preference profile, resolved from the Control Plane and injected into your context before
you run. Its writablePreferences list is the complete set of canonical preferences you may update.

Long-term preferences describe the USER, not you. Speak about the user in the second person (for
example, "You prefer a window seat") and never adopt their preferences as your own. Map a user's
statement to the single best entry in writablePreferences and call save_preference with that entry
as the attribute; the platform resolves the owning schema. Never ask for schema IDs, never write an
attribute outside writablePreferences, and never invent preferences the user did not state.
"""


def build_control_plane_api_client() -> ControlPlaneApiClient:
    """Long-term memory client — governed preference profiles via the runtime API."""
    if settings.control_plane_api_token:
        token_provider = StaticTokenProvider(settings.control_plane_api_token)
    elif settings.control_plane_api_audience:
        token_provider = GoogleIdTokenProvider(settings.control_plane_api_audience)
    else:
        token_provider = StaticTokenProvider(None)
    return ControlPlaneApiClient(
        base_url=settings.control_plane_api_url, token_provider=token_provider
    )


def _identity(context: Any) -> tuple[str, str]:
    session = getattr(context, "session", None)
    user_id = getattr(context, "user_id", None) or getattr(session, "user_id", None)
    session_id = getattr(session, "id", None)
    if not user_id or not session_id:
        raise ValueError("ADK context does not contain a user ID and session ID")
    return str(user_id), str(session_id)


async def _resolve_snapshot(context: Any) -> dict[str, Any]:
    user_id, session_id = _identity(context)
    snapshot = await build_control_plane_api_client().resolve_preferences(
        user_id=user_id,
        session_id=session_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        include_provenance=True,
    )
    payload = snapshot.model_dump(by_alias=True, mode="json")
    context.state[SNAPSHOT_STATE_KEY] = payload
    return payload


async def initialize_preference_snapshot(callback_context: CallbackContext) -> None:
    """Resolve the effective long-term snapshot once, before the first model call in a Session."""
    if not isinstance(callback_context.state.get(SNAPSHOT_STATE_KEY), dict):
        await _resolve_snapshot(callback_context)


async def inject_preference_snapshot(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Add the authorized long-term preference snapshot to Gemini's system context."""
    snapshot = callback_context.state.get(SNAPSHOT_STATE_KEY)
    if isinstance(snapshot, dict):
        llm_request.append_instructions(
            [
                "Effective user preference snapshot for this Session (JSON):\n"
                + json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
            ]
        )


async def save_preference(
    attribute: str,
    value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Persist a long-term preference to the governed profile; the platform resolves its schema."""
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().update_preference(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        attribute=attribute,
        value=value,
    )
    snapshot = await _resolve_snapshot(tool_context)
    return {
        "mutation": mutation.model_dump(by_alias=True, mode="json"),
        "snapshot": snapshot,
    }


root_agent = Agent(
    name="dual_memory_agent",
    model=Gemini(model=settings.model),
    instruction=INSTRUCTION,
    tools=[save_preference],
    before_agent_callback=initialize_preference_snapshot,
    before_model_callback=inject_preference_snapshot,
)

# Exposed for `adk web` / `adk api_server` discovery.
app = App(name=settings.app_name, root_agent=root_agent)


def build_session_service() -> DatabaseSessionService:
    """Short-term memory: ADK sessions persisted in Cloud SQL / PostgreSQL."""
    return DatabaseSessionService(db_url=settings.sessions_database_url)


def build_runner() -> Runner:
    """Compose the agent with short-term (Postgres) sessions; long-term is the Control Plane.

    ``memory_service`` is None on purpose: long-term memory is the governed preference profile
    reached through the runtime API, not ADK Memory Bank.
    """
    return Runner(
        agent=root_agent,
        app_name=settings.app_name,
        session_service=build_session_service(),
        memory_service=None,
    )
