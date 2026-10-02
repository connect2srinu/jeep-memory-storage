"""ADK agent with split memory: short-term in Postgres, long-term as governed preferences.

Short-term (session/conversation) state is persisted by ADK's ``DatabaseSessionService`` into
Cloud SQL / PostgreSQL. Long-term memory is NOT ADK Memory Bank here: it is the Control Plane's
structured, governed preference profiles (e.g. ``{domain}-preferences-v1`` schemas). The agent
resolves the effective preference snapshot for the Session before the model runs and writes new
preferences back through the runtime API, so long-term memory always lands in the defined schemas.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

from google.adk import Runner
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini, LlmRequest
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import ToolContext

from .client import (
    ControlPlaneApiClient,
    ControlPlaneApiError,
    GoogleIdTokenProvider,
    StaticTokenProvider,
)
from .settings import settings

SNAPSHOT_STATE_KEY = "shared_memory:effective_snapshot"

logger = logging.getLogger("memory_agent.memory_decision")
# Emails and digit runs (phone, card, account numbers) are masked even in non-sensitive log values.
_IDENTIFIERS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\d[\d\s().-]{3,}\d")

INSTRUCTION = f"""
You are a helpful assistant for the {settings.consumer_domain} domain with two kinds of memory.

Short-term memory is the current conversation (this Session). Long-term memory is the customer's
governed preference profile, resolved from the Control Plane and injected into your context before
you run as an "Effective user preference snapshot" JSON. It holds:
- "preferences": current values — household-wide ones plus the customer's own per-person ones.
- "writablePreferenceDetails": the attributes you may save, each with a "level", a "description"
  (its meaning), "health" (true for health data such as allergies) and "dataType".
- "approvedTopics" / "approvedTopicDetails": non-canonical categories you may retain.
- "householdMembers": the people in the customer's household — memberId, displayName,
  relationship, memberKind (ROOT = the customer, DEPENDENT = a child, PROXY_ADULT = another adult),
  minor, status ("provisional" = proposed, not yet confirmed), aliases (other names for them), and
  isSelf (true for the customer you are talking to).

Talk about the customer in the second person ("You prefer...") and never adopt their preferences.

READING. To answer questions about preferences, read the snapshot or call get_preferences. For
another household member, call get_preferences with that person's member_id. If a value is not
present, say so plainly — do not guess.

SAVING. Pick the attribute whose description best matches the statement:
- A dislike or preference ("doesn't like peanuts", "prefers oat milk") is NOT health data — use a
  non-health attribute. Only an allergy, intolerance or medical need is health data (health=true).
  Never turn a dislike into an allergy.
- dataType "list" (e.g. several brands or restrictions): call save_preference once per item, with
  the item alone as the value; it is added to what is already saved. When the customer says an
  item no longer applies, call save_preference with that item and remove=true.
- level "household": shared by everyone — call save_preference with no member.
- level "household_member" (about one person):
  - About the customer themself: pass no member.
  - About someone else: pass member_id if that person is in householdMembers (match their name or
    aliases); otherwise pass member_name (and relationship, e.g. "son", if the customer said it).
    Never invent a member_id, and never ask the customer for one — they don't know member ids.
- Otherwise, if it fits an approved topic, call remember_dynamic_preference with that topic.
- Otherwise do not store it: call record_memory_decision, then explain that this kind of
  information isn't something you can save yet (for example, if there is no attribute for dislikes,
  say so — don't save it as an allergy).

RECORDING DECISIONS. Whenever the customer states a preference or a fact about themselves or their
household, or asks you to remember something, and you decide NOT to save it, call
record_memory_decision with a short paraphrase and the reason. Do not call it for ordinary shopping
requests.

WHAT THE PLATFORM RETURNS. Every write returns a "status":
- updated / added / merged / moved / forgotten / exists: done — tell the customer briefly.
- needs_confirmation: NOTHING was saved. Ask the customer exactly the "confirmationPrompt" and stop.
  Only if they clearly say yes, call the same tool again with the same values, plus the returned
  member_id, and confirmed=true. If they say no, call record_memory_decision (reason: the customer
  said no) and tell them nothing was saved.
- ambiguous: NOTHING was saved. Ask the "confirmationPrompt" (which person they mean). Then repeat
  with the chosen person's member_id, or add a new person with add_household_member.
- not_allowed: NOTHING was saved. Explain the "message". For another adult's allergy, offer to save
  it as a household-level product exclusion instead (a household attribute), and mention they can
  save their own allergy from their own account.
Never pass confirmed=true unless the customer has just answered yes to that exact question.

MANAGING PEOPLE (only when the customer asks):
- Add someone: add_household_member (confirmed=true only if they explicitly asked to add them).
- Rename someone, or correct whether they are a minor: update_household_member.
- Two entries are the same person: merge_household_members (keep the right one).
- A value was saved for the wrong person: move_preference.
- Delete a saved value (this also withdraws consent for health data): forget_preference.
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


def _snapshot_key(member_id: str | None = None) -> str:
    """Cache the top-level snapshot and each member's snapshot under their own key."""
    if member_id:
        return f"{SNAPSHOT_STATE_KEY}:m:{member_id}"
    return SNAPSHOT_STATE_KEY


async def _resolve_snapshot(context: Any, member_id: str | None = None) -> dict[str, Any]:
    user_id, session_id = _identity(context)
    snapshot = await build_control_plane_api_client().resolve_preferences(
        user_id=user_id,
        session_id=session_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        include_provenance=True,
        member_id=member_id,
    )
    payload = snapshot.model_dump(by_alias=True, mode="json")
    context.state[_snapshot_key(member_id)] = payload
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
    member_id: str | None = None,
) -> dict[str, Any]:
    """Return the user's current governed preferences and the memory scope in effect.

    Use this to answer any question about what the user's preferences or memory currently hold.
    Returns the effective snapshot: current values ("preferences"), the canonical attributes that may
    be updated ("writablePreferences" / "writablePreferenceDetails"), the approved dynamic topics
    ("approvedTopics" / "approvedTopicDetails"), and the household roster ("householdId" /
    "householdMembers").

    Pass ``member_id`` (from "householdMembers") to read a specific household member's preferences,
    e.g. a child's allergies; omit it for the customer's own preferences.
    """
    snapshot = tool_context.state.get(_snapshot_key(member_id))
    if isinstance(snapshot, dict):
        return snapshot
    return await _resolve_snapshot(tool_context, member_id)


def _log_decision(
    tool_context: ToolContext, *, decision: str, value: object, masked: bool, **fields: object
) -> None:
    """Emit one agent-side event per memory decision: saved, not saved, or declined by the model.

    The value is masked entirely for health, sensitive, and rejected items; otherwise identifiers
    (emails, digit runs) are masked and the text is truncated.
    """
    user_id, session_id = _identity(tool_context)
    text = str(value)
    logger.info(
        json.dumps(
            {
                "event": "agent_memory_decision",
                "decision": decision,
                "value": "***" if masked else _IDENTIFIERS.sub("***", text)[:200],
                "value_length": len(text),
                "agent_id": settings.agent_id,
                "user_id": user_id,
                "session_id": session_id,
                **fields,
            },
            sort_keys=True,
            default=str,
        )
    )


def _snapshot_entry(tool_context: ToolContext, section: str, field: str, name: str) -> dict[str, Any]:
    """The snapshot's details for one writable attribute or approved topic, if listed."""
    snapshot = tool_context.state.get(SNAPSHOT_STATE_KEY) or {}
    return next(
        (
            item
            for item in snapshot.get(section, [])
            if item.get(field) == name or str(item.get(field, "")).endswith(f".{name}")
        ),
        {},
    )


async def _result(
    tool_context: ToolContext, mutation: Any, member_id: str | None = None
) -> dict[str, Any]:
    """Refresh the cached snapshots after a change so the next model turn sees it."""
    snapshot = await _resolve_snapshot(tool_context)
    if member_id and member_id != snapshot.get("actingMemberId"):
        await _resolve_snapshot(tool_context, member_id)
    return {"result": mutation.model_dump(by_alias=True, mode="json")}


async def save_preference(
    attribute: str,
    value: str,
    tool_context: ToolContext,
    member_id: str | None = None,
    member_name: str | None = None,
    relationship: str | None = None,
    confirmed: bool = False,
    remove: bool = False,
) -> dict[str, Any]:
    """Save a canonical preference; the platform resolves its schema and scope level.

    For a "household_member"-level attribute about someone other than the customer, pass member_id
    (from householdMembers) or, if they are not listed, member_name plus relationship (e.g. "son").
    Pass neither for the customer themself or for "household"-level attributes.
    For a dataType "list" attribute, value is ONE item: it is added to the list, or removed from it
    with remove=true. Call once per item.
    Check the returned status: "needs_confirmation" and "ambiguous" mean nothing was saved — ask
    the customer the confirmationPrompt first. Set confirmed=true only after they said yes to it.
    """
    user_id, _ = _identity(tool_context)
    detail = _snapshot_entry(tool_context, "writablePreferenceDetails", "attribute", attribute)
    health = bool(detail.get("health"))
    fields = {
        "tool": "save_preference",
        "correlation_id": str(uuid4()),
        "preference_type": "canonical",
        "key": attribute,
        "level": detail.get("level"),
        "health": health,
        "relationship": relationship,
        "confirmed": confirmed,
        "remove": remove,
    }
    try:
        mutation = await build_control_plane_api_client().update_preference(
            user_id=user_id,
            app_name=settings.app_name,
            consumer_domain=settings.consumer_domain,
            agent_id=settings.agent_id,
            attribute=attribute,
            value=value,
            member_id=member_id,
            member_name=member_name,
            relationship=relationship,
            confirmed=confirmed,
            correlation_id=fields["correlation_id"],
            remove=remove,
        )
    except ControlPlaneApiError as error:
        _log_decision(
            tool_context,
            decision="rejected",
            value=value,
            masked=True,
            reason=str(error),
            http_status=error.status_code,
            member_id=member_id,
            **fields,
        )
        raise
    _log_decision(
        tool_context,
        decision=mutation.status,
        value=value,
        masked=health,
        reason=mutation.message,
        reference=mutation.reference,
        value_version=mutation.profile_version,
        member_id=mutation.member_id or member_id,
        **fields,
    )
    return await _result(tool_context, mutation, mutation.member_id)


async def forget_preference(
    attribute: str,
    tool_context: ToolContext,
    member_id: str | None = None,
) -> dict[str, Any]:
    """Delete one saved value (member_id for another household member; omit for the customer).

    Deleting health data also withdraws the consent recorded for it.
    """
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().forget_preference(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        attribute=attribute,
        member_id=member_id,
    )
    return await _result(tool_context, mutation, member_id)


async def add_household_member(
    name: str,
    tool_context: ToolContext,
    relationship: str | None = None,
    member_id: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Add a person to the customer's household (the platform checks for an existing match).

    Use confirmed=true only when the customer explicitly asked to add them, or answered yes to the
    returned confirmationPrompt (then also pass the returned member_id).
    """
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().add_household_member(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        name=name,
        relationship=relationship,
        member_id=member_id,
        confirmed=confirmed,
    )
    return await _result(tool_context, mutation)


async def update_household_member(
    member_id: str,
    tool_context: ToolContext,
    display_name: str | None = None,
    is_minor: bool | None = None,
) -> dict[str, Any]:
    """Rename a household member (the old name is kept as an alias) or correct whether they are a
    minor (e.g. an adult son)."""
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().update_household_member(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        member_id=member_id,
        display_name=display_name,
        minor=is_minor,
    )
    return await _result(tool_context, mutation)


async def merge_household_members(
    keep_member_id: str,
    merge_member_id: str,
    tool_context: ToolContext,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Merge two entries that are the same person: keep_member_id stays, merge_member_id's values
    move to it and its name becomes an alias. Ask the confirmationPrompt first."""
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().merge_household_members(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        keep_member_id=keep_member_id,
        merge_member_id=merge_member_id,
        confirmed=confirmed,
    )
    return await _result(tool_context, mutation, keep_member_id)


async def move_preference(
    attribute: str,
    to_member_id: str,
    tool_context: ToolContext,
    from_member_id: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Move one per-person value saved for the wrong person (from_member_id; omit for the
    customer) to to_member_id. Ask the confirmationPrompt first."""
    user_id, _ = _identity(tool_context)
    mutation = await build_control_plane_api_client().move_preference(
        user_id=user_id,
        app_name=settings.app_name,
        consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id,
        attribute=attribute,
        from_member_id=from_member_id,
        to_member_id=to_member_id,
        confirmed=confirmed,
    )
    if from_member_id:
        await _resolve_snapshot(tool_context, from_member_id)
    return await _result(tool_context, mutation, to_member_id)


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
    detail = _snapshot_entry(tool_context, "approvedTopicDetails", "topic", topic)
    sensitive = detail.get("sensitivity", "normal") != "normal"
    fields = {
        "tool": "remember_dynamic_preference",
        "correlation_id": str(uuid4()),
        "preference_type": "dynamic",
        "key": f"topic:{topic}",
        "sensitivity": detail.get("sensitivity"),
    }
    try:
        mutation = await build_control_plane_api_client().write_dynamic_memory(
            user_id=user_id,
            app_name=settings.app_name,
            consumer_domain=settings.consumer_domain,
            agent_id=settings.agent_id,
            topic=topic,
            value=value,
            correlation_id=fields["correlation_id"],
        )
    except ControlPlaneApiError as error:
        _log_decision(
            tool_context,
            decision="rejected",
            value=value,
            masked=True,
            reason=str(error),
            http_status=error.status_code,
            **fields,
        )
        raise
    _log_decision(
        tool_context,
        decision=mutation.status,
        value=value,
        masked=sensitive,
        reference=mutation.reference,
        value_version=mutation.profile_version,
        **fields,
    )
    return await _result(tool_context, mutation)


async def record_memory_decision(
    statement: str,
    reason: str,
    tool_context: ToolContext,
    sensitive: bool = False,
) -> dict[str, Any]:
    """Record that you decided NOT to save something the customer said. Nothing is stored.

    Call this when the customer states a preference or a fact about themselves or their household,
    or asks you to remember something, and you won't save it — because no writablePreferences
    attribute or approved topic fits, it isn't a lasting preference, or they said no to a
    confirmationPrompt. Don't call it for ordinary shopping requests.
    statement: a short paraphrase of what was not saved. reason: why.
    sensitive: true for health, religion, ethnicity, sexual orientation, finances, or identifiers.
    """
    _log_decision(
        tool_context,
        decision="declined",
        value=statement,
        masked=sensitive,
        tool="record_memory_decision",
        preference_type="none",
        reason=reason,
        sensitive=sensitive,
    )
    return {"recorded": True, "saved": False}


root_agent = Agent(
    name="dual_memory_agent",
    model=Gemini(model=settings.model),
    instruction=INSTRUCTION,
    tools=[
        get_preferences,
        save_preference,
        remember_dynamic_preference,
        record_memory_decision,
        forget_preference,
        add_household_member,
        update_household_member,
        merge_household_members,
        move_preference,
    ],
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
