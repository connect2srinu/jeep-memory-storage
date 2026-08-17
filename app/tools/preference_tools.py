from __future__ import annotations

from typing import Any

from app.agents.grocery_extraction import extract_grocery_candidate
from app.shared_memory.bootstrap import platform_dependencies
from app.shared_memory.models import PreferenceCandidate, PreferenceScope

CONSUMER_DOMAIN = "grocery"
AGENT_ID = "grocery-agent"


def _identity(tool_context: Any) -> tuple[str, str]:
    session = getattr(tool_context, "session", None)
    user_id = getattr(tool_context, "user_id", None) or getattr(session, "user_id", None)
    session_id = getattr(session, "id", None)
    if not user_id:
        user_id = tool_context.state.get("preference_user_id")
    if not session_id:
        session_id = tool_context.state.get("preference_session_id")
    if not user_id or not session_id:
        raise ValueError("ADK tool context does not contain a user ID and session ID")
    return str(user_id), str(session_id)


async def get_effective_preferences(tool_context: Any) -> dict[str, Any]:
    """Resolve a single authorized context through the Shared Memory Platform."""
    user_id, session_id = _identity(tool_context)
    platform = platform_dependencies.for_tool_context(tool_context)
    context = await platform.get_effective_context(
        user_id=user_id,
        session_id=session_id,
        consumer_domain=CONSUMER_DOMAIN,
        agent_id=AGENT_ID,
        use_snapshot=False,
    )
    return context.to_dict()


async def set_session_preference(key: str, value: Any, tool_context: Any) -> dict[str, Any]:
    """Submit an explicitly temporary Grocery preference to platform policy."""
    user_id, session_id = _identity(tool_context)
    platform = platform_dependencies.for_tool_context(tool_context)
    candidate = PreferenceCandidate(
        key=key,
        value=value,
        proposed_domain=CONSUMER_DOMAIN,
        requested_scope=PreferenceScope.SESSION,
        confidence=1.0,
        source="GROCERY_AGENT_TOOL",
        source_message=f"direct session preference: {key}",
        user_id=user_id,
        session_id=session_id,
        explicit=True,
        evidence="direct explicit tool call",
    )
    return (
        await platform.submit_preference(
            candidate=candidate,
            consumer_domain=CONSUMER_DOMAIN,
            agent_id=AGENT_ID,
        )
    ).to_dict()

async def process_preference_statement(message: str, tool_context: Any) -> dict[str, Any]:
    """Extract a candidate; platform policy controls the resulting write or routing."""
    user_id, session_id = _identity(tool_context)
    candidate = extract_grocery_candidate(message, user_id=user_id, session_id=session_id)
    if candidate is None:
        return {"status": "NO_CANDIDATE"}
    platform = platform_dependencies.for_tool_context(tool_context)
    return (
        await platform.submit_preference(
            candidate=candidate,
            consumer_domain=CONSUMER_DOMAIN,
            agent_id=AGENT_ID,
        )
    ).to_dict()
