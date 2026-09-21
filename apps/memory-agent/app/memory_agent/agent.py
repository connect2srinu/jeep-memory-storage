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
you run as an "Effective user preference snapshot" JSON. That snapshot holds the current values
(its "preferences" object), the canonical attributes you may update ("writablePreferences", each
annotated in "writablePreferenceDetails" with a "level" of "member" or "dependent"), the approved
non-canonical topics ("approvedTopics"), and the member's dependents ("dependents", a list of
{{dependentId, displayName}} — e.g. their children).

Each writable attribute has a "level" in writablePreferenceDetails:
- "member": the acting user's own attribute — pass no id.
- "household": shared by the whole household — pass no id.
- "dependent": a child's attribute — look the named child up in "dependents" to get its dependentId
  and pass dependentId.
- "household_member": a specific household member's attribute — look the named person up in
  "householdMembers" to get its memberId and pass memberId. Writing another member requires the
  caller to be their guardian; the platform enforces this.
Only use a dependentId/memberId that appears in the snapshot's lists — never invent one. If a
per-person attribute is requested but you cannot tell which dependent or member is meant, ask which
one before saving.

To ANSWER any question about the user's current preferences or memory (for example "what are my
preferences?" or "show active preferences"), call get_preferences. It returns the same snapshot —
the current values ("preferences"), the canonical attributes you may update ("writablePreferences"),
and the approved topics ("approvedTopics"). The snapshot is also already in your context, so you may
read it directly too. If a value is not present, say so plainly — do not guess or refuse.

Long-term preferences describe the USER, not you. Speak about the user in the second person (for
example, "You prefer a window seat") and never adopt their preferences as your own.

When the user asks you to remember, save, or update something, decide in this order:
1. If it maps to an entry in writablePreferences, call save_preference with that attribute
   (canonical, governed). Use writablePreferenceDetails — each has the attribute, its level, and its
   meaning (description) — to choose the attribute whose description best matches the statement. The
   platform resolves the owning schema. If that attribute's level is "dependent", also pass the
   dependentId of the dependent the statement is about.
2. Otherwise, if it clearly belongs to one of the snapshot's approvedTopics, call
   remember_dynamic_preference with that exact topic. These are the only non-canonical categories
   you may retain. Use approvedTopicDetails — each has the topic, its meaning (description), and its
   sensitivity — to pick the topic whose description best matches the user's statement.
3. Otherwise, do not store it. Explain that it is not an approved memory type. Never ask for schema
   IDs, never invent an attribute or a topic outside these lists, and never store facts the user
   did not state.
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


def _snapshot_key(dependent_id: str | None = None, member_id: str | None = None) -> str:
    """Cache the top-level snapshot and each dependent's/member's snapshot under their own key."""
    if member_id:
        return f"{SNAPSHOT_STATE_KEY}:m:{member_id}"
    if dependent_id:
        return f"{SNAPSHOT_STATE_KEY}:d:{dependent_id}"
    return SNAPSHOT_STATE_KEY


async def _resolve_snapshot(
    context: Any, dependent_id: str | None = None, member_id: str | None = None
) -> dict[str, Any]:
    user_id, session_id = _identity(context)
    snapshot = await build_control_plane_api_client().resolve_preferences(
        user_id=user_id,
        session_id=session_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        include_provenance=True,
        dependent_id=dependent_id,
        member_id=member_id,
    )
    payload = snapshot.model_dump(by_alias=True, mode="json")
    context.state[_snapshot_key(dependent_id, member_id)] = payload
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


async def get_preferences(
    tool_context: ToolContext,
    dependent_id: str | None = None,
    member_id: str | None = None,
) -> dict[str, Any]:
    """Return the user's current governed preferences and the memory scope in effect.

    Use this to answer any question about what the user's preferences or memory currently hold.
    Returns the effective snapshot: current values ("preferences"), the canonical attributes that may
    be updated ("writablePreferences" / "writablePreferenceDetails"), the approved dynamic topics
    ("approvedTopics" / "approvedTopicDetails"), the member's dependents ("dependents"), and the
    household roster ("householdId" / "householdMembers").

    Pass ``dependent_id`` (from "dependents") or ``member_id`` (from "householdMembers") to read a
    specific dependent's or household member's preferences, e.g. a child's allergies; omit both for
    the acting member's own top-level preferences.
    """
    snapshot = tool_context.state.get(_snapshot_key(dependent_id, member_id))
    if isinstance(snapshot, dict):
        return snapshot
    return await _resolve_snapshot(tool_context, dependent_id, member_id)


async def save_preference(
    attribute: str,
    value: str,
    tool_context: ToolContext,
    dependent_id: str | None = None,
    member_id: str | None = None,
) -> dict[str, Any]:
    """Persist a canonical long-term preference; the platform resolves its writable schema.

    Use the attribute's "level" in the snapshot's "writablePreferenceDetails":
    - "member" / "household": pass neither id.
    - "dependent": pass ``dependent_id`` from the "dependents" list (e.g. a child's allergies).
    - "household_member": pass ``member_id`` from the "householdMembers" list (the person the
      statement is about). Writing another member requires the caller to be their guardian.
    The platform enforces the scope level and the guardian check.
    """
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().update_preference(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        attribute=attribute,
        value=value,
        dependent_id=dependent_id,
        member_id=member_id,
    )
    snapshot = await _resolve_snapshot(tool_context, dependent_id, member_id)
    return {
        "mutation": mutation.model_dump(by_alias=True, mode="json"),
        "snapshot": snapshot,
    }


async def remember_dynamic_preference(
    topic: str,
    value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Persist a non-canonical preference within an approved dynamic-memory topic.

    The platform rejects any topic outside the snapshot's approvedTopics, so pass a topic from
    that list. Use this only when no writablePreferences entry fits the request.
    """
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().write_dynamic_memory(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        topic=topic,
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
    tools=[get_preferences, save_preference, remember_dynamic_preference],
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
