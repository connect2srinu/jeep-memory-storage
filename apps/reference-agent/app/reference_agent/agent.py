from __future__ import annotations

import json
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini, LlmRequest
from google.adk.tools import ToolContext

from .client import (
    EffectivePreferenceSnapshot,
    GoogleIdTokenProvider,
    MemoryApiClient,
    PreferenceCandidate,
    StaticTokenProvider,
)
from .settings import settings

SNAPSHOT_STATE_KEY = "shared_memory:effective_snapshot"


def build_memory_api_client() -> MemoryApiClient:
    """Build the client without exposing Memory Bank or provider SDKs to the agent."""
    if settings.memory_api_token:
        token_provider = StaticTokenProvider(settings.memory_api_token)
    elif settings.memory_api_audience:
        token_provider = GoogleIdTokenProvider(settings.memory_api_audience)
    else:
        token_provider = StaticTokenProvider(None)
    return MemoryApiClient(base_url=settings.memory_api_url, token_provider=token_provider)


def _identity(context: Any) -> tuple[str, str]:
    session = getattr(context, "session", None)
    user_id = getattr(context, "user_id", None) or getattr(session, "user_id", None)
    session_id = getattr(session, "id", None)
    if not user_id or not session_id:
        raise ValueError("ADK context does not contain a user ID and session ID")
    return str(user_id), str(session_id)


def _snapshot_payload(snapshot: EffectivePreferenceSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(by_alias=True, mode="json")


async def _load_snapshot(context: Any, *, refresh: bool) -> dict[str, Any]:
    user_id, session_id = _identity(context)
    client = build_memory_api_client()
    operation = client.refresh_preferences if refresh else client.resolve_preferences
    snapshot = await operation(
        user_id=user_id,
        session_id=session_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
    )
    payload = _snapshot_payload(snapshot)
    context.state[SNAPSHOT_STATE_KEY] = payload
    return payload


async def initialize_preference_snapshot(callback_context: CallbackContext) -> None:
    """Resolve the effective snapshot once, before the first model call in a Session."""
    if not isinstance(callback_context.state.get(SNAPSHOT_STATE_KEY), dict):
        await _load_snapshot(callback_context, refresh=False)


async def inject_preference_snapshot(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Add the authorized Session snapshot to Gemini's system context."""
    snapshot = callback_context.state.get(SNAPSHOT_STATE_KEY)
    if isinstance(snapshot, dict):
        llm_request.append_instructions(
            [
                "Effective user preference snapshot for this Session (JSON):\n"
                + json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
            ]
        )


async def get_user_preferences(tool_context: ToolContext) -> dict[str, Any]:
    """Return the effective preferences cached for this Session."""
    snapshot = tool_context.state.get(SNAPSHOT_STATE_KEY)
    if isinstance(snapshot, dict):
        return snapshot
    return await _load_snapshot(tool_context, refresh=False)


async def refresh_user_preferences(tool_context: ToolContext) -> dict[str, Any]:
    """Explicitly refresh the Session snapshot from the Shared Memory API."""
    return await _load_snapshot(tool_context, refresh=True)


async def update_user_preference(
    attribute: str,
    schema_id: str,
    value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Save one canonical preference, then refresh and return the effective Session snapshot."""
    user_id, _ = _identity(tool_context)
    mutation = await build_memory_api_client().update_preference(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        schema_id=schema_id,
        attribute=attribute,
        value=value,
    )
    snapshot = await _load_snapshot(tool_context, refresh=True)
    return {
        "mutation": mutation.model_dump(by_alias=True, mode="json"),
        "snapshot": snapshot,
    }


async def submit_preference_event(
    text: str,
    attribute: str,
    schema_id: str,
    value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Submit a user statement with one candidate, then refresh the effective snapshot."""
    user_id, _ = _identity(tool_context)
    mutation = await build_memory_api_client().ingest_event(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        text=text,
        candidates=[PreferenceCandidate(schema_id=schema_id, attribute=attribute, value=value)],
    )
    snapshot = await _load_snapshot(tool_context, refresh=True)
    return {
        "mutation": mutation.model_dump(by_alias=True, mode="json"),
        "snapshot": snapshot,
    }


INSTRUCTION = """
You are Grocery Preference Assistant, a reference consumer of the Shared Memory API.
The effective preference snapshot is loaded into Session state before Gemini runs and is included
in model context. Use get_user_preferences when you need the structured values. Call
refresh_user_preferences only when the user explicitly requests a refresh. Use
update_user_preference for an explicit canonical preference update and submit_preference_event for
a natural-language memory event with a candidate; both tools refresh after a successful change.
Never fabricate absent preferences and never attempt to query Memory Bank directly.
"""

root_agent = Agent(
    name="grocery_preference_assistant",
    model=Gemini(model=settings.model),
    instruction=INSTRUCTION,
    tools=[
        get_user_preferences,
        refresh_user_preferences,
        update_user_preference,
        submit_preference_event,
    ],
    before_agent_callback=initialize_preference_snapshot,
    before_model_callback=inject_preference_snapshot,
)

app = App(name=settings.app_name, root_agent=root_agent)
