from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini, LlmRequest
from google.adk.tools import ToolContext

from .client import (
    ControlPlaneApiClient,
    EffectivePreferenceSnapshot,
    GoogleIdTokenProvider,
    PreferenceCandidate,
    StaticTokenProvider,
)
from .settings import settings

SNAPSHOT_STATE_KEY = "shared_memory:effective_snapshot"
logger = logging.getLogger("reference_agent.preference_snapshot")


def _log_flow_step(step: str, **fields: Any) -> None:
    logger.info(
        json.dumps(
            {"flow": "effective_preference_snapshot", "step": step, **fields},
            sort_keys=True,
            default=str,
        )
    )


def build_control_plane_api_client() -> ControlPlaneApiClient:
    """Build the client without exposing Memory Bank or provider SDKs to the agent."""
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


def _snapshot_payload(snapshot: EffectivePreferenceSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(by_alias=True, mode="json")


async def _load_snapshot(context: Any, *, refresh: bool) -> dict[str, Any]:
    user_id, session_id = _identity(context)
    client = build_control_plane_api_client()
    operation = client.refresh_preferences if refresh else client.resolve_preferences
    endpoint = (
        "/api/v1/runtime/preferences/refresh" if refresh else "/api/v1/runtime/preferences/resolve"
    )
    _log_flow_step(
        "reference_agent_request",
        agent_id=settings.agent_id,
        domain=settings.consumer_domain,
        endpoint=endpoint,
        session_id=session_id,
        user_id=user_id,
    )
    snapshot = await operation(
        user_id=user_id,
        session_id=session_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        include_provenance=True,
    )
    payload = _snapshot_payload(snapshot)
    _log_flow_step(
        "effective_snapshot_received",
        agent_id=snapshot.agent_id,
        policy_version=snapshot.policy_version,
        preference_count=len(snapshot.preferences),
        schema_count=len(snapshot.schema_versions),
        session_id=session_id,
        snapshot_version=snapshot.snapshot_version,
        writable_preference_count=len(snapshot.writable_preferences),
    )
    context.state[SNAPSHOT_STATE_KEY] = payload
    _log_flow_step(
        "snapshot_cached_in_adk_session_state",
        session_id=session_id,
        snapshot_state_key=SNAPSHOT_STATE_KEY,
        snapshot_version=snapshot.snapshot_version,
    )
    logger.info(
        "SNAPSHOT_STATE_KEY=%s snapshotVersion=%s sessionId=%s",
        SNAPSHOT_STATE_KEY,
        snapshot.snapshot_version,
        session_id,
    )
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
    """Explicitly refresh the Session snapshot from the Control Plane API."""
    return await _load_snapshot(tool_context, refresh=True)


async def update_user_preference(
    attribute: str,
    value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Save a preference; the platform resolves its authorized writable schema."""
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().update_preference(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
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
    value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Submit a user statement with one candidate, then refresh the effective snapshot."""
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().ingest_event(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        text=text,
        candidates=[PreferenceCandidate(attribute=attribute, value=value)],
    )
    snapshot = await _load_snapshot(tool_context, refresh=True)
    return {
        "mutation": mutation.model_dump(by_alias=True, mode="json"),
        "snapshot": snapshot,
    }


INSTRUCTION = f"""
You are the preference assistant for the {settings.consumer_domain} domain and a reference consumer
of the Control Plane API. Users describe preferences naturally and must never be asked for schema
IDs or canonical attribute IDs. The effective preference snapshot is loaded into Session state
before Gemini runs and is included in model context. Its writablePreferences list is the complete
set of canonical preferences this agent may update. Map the user's statement to the single best
entry in writablePreferences and pass that entry as attribute. The platform resolves the owning
writable schema behind the scenes; never guess or request a schema ID.

Use get_user_preferences when you need the structured values. Call refresh_user_preferences only
when the user explicitly requests a refresh. Use
update_user_preference for an explicit canonical preference update and submit_preference_event for
a natural-language memory event with a candidate; both tools refresh after a successful change.
Never fabricate absent preferences, never write an attribute outside writablePreferences, and never
attempt to query Memory Bank directly. If no writable preference clearly matches the request, explain
that the preference must be onboarded instead of inventing an attribute.
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
