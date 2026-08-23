from __future__ import annotations

from typing import Any

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini

from .client import MemoryApiClient
from .settings import settings

SNAPSHOT_STATE_KEY = "shared_memory:effective_snapshot"


def _identity(tool_context: Any) -> tuple[str, str]:
    session = getattr(tool_context, "session", None)
    user_id = getattr(tool_context, "user_id", None) or getattr(session, "user_id", None)
    session_id = getattr(session, "id", None)
    if not user_id or not session_id:
        raise ValueError("ADK tool context does not contain a user ID and session ID")
    return str(user_id), str(session_id)


async def refresh_user_preferences(tool_context: Any) -> dict[str, Any]:
    """Resolve through the Memory API and replace the Session snapshot."""
    user_id, session_id = _identity(tool_context)
    client = MemoryApiClient(
        base_url=settings.memory_api_url,
        token=settings.memory_api_token,
    )
    snapshot = await client.resolve_preferences(
        user_id=user_id,
        session_id=session_id,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
    )
    tool_context.state[SNAPSHOT_STATE_KEY] = snapshot
    return snapshot


async def get_user_preferences(tool_context: Any) -> dict[str, Any]:
    """Return the cached Session snapshot, resolving once when it is absent."""
    snapshot = tool_context.state.get(SNAPSHOT_STATE_KEY)
    if isinstance(snapshot, dict):
        return snapshot
    return await refresh_user_preferences(tool_context)


INSTRUCTION = """
You are Grocery Preference Assistant, a reference consumer of the Shared Memory API.
Use get_user_preferences before reporting or applying user preferences. The tool caches the
effective snapshot in ADK Session state; call refresh_user_preferences only when the user requests
a refresh or after a preference update. Never fabricate absent preferences and never attempt to
query Memory Bank directly.
"""

root_agent = Agent(
    name="grocery_preference_assistant",
    model=Gemini(model=settings.model),
    instruction=INSTRUCTION,
    tools=[get_user_preferences, refresh_user_preferences],
)

app = App(name=settings.app_name, root_agent=root_agent)
