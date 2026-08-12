from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.preferences.candidate_extractor import extract_candidate
from app.preferences.memory_service import (
    LongTermPreferenceService,
    MemoryBankNotConfiguredError,
)
from app.preferences.models import PreferenceScope
from app.services.preference_context_service import PreferenceContextService

_ALLOWED_KEYS = {
    "allow_substitutions",
    "budget",
    "diet",
    "organic",
    "preferred_brand",
    "preferred_milk",
    "preferred_product",
    "preferred_store",
}


@dataclass(slots=True)
class ToolRuntime:
    context_service: PreferenceContextService
    memory_service: LongTermPreferenceService
    agent_id: str
    domain: str


_runtime: ToolRuntime | None = None


def configure_runtime(runtime: ToolRuntime) -> None:
    global _runtime
    _runtime = runtime


def _configured() -> ToolRuntime:
    global _runtime
    if _runtime is None:
        # Agent Runtime unpickles tool callables in a fresh worker process, so
        # module globals configured during local app construction are absent.
        # Rebuild infrastructure adapters lazily from runtime-provided env vars.
        from app.config import settings
        from app.preferences.memory_service import EnvironmentMemoryBankPreferenceService
        from app.preferences.models import Preference, PreferenceSource
        from app.preferences.profile_service import MockProfilePreferenceService
        from app.preferences.resolver import PreferenceResolver

        memory_service = EnvironmentMemoryBankPreferenceService(
            project=settings.project,
            location=settings.location,
            agent_engine_id=settings.memory_resource_id,
        )
        context_service = PreferenceContextService(
            profile_service=MockProfilePreferenceService(),
            memory_service=memory_service,
            session_store=None,
            resolver=PreferenceResolver(settings.minimum_memory_confidence),
            defaults=(
                Preference(
                    "allow_substitutions",
                    False,
                    PreferenceSource.DEFAULT,
                    domain=settings.domain,
                ),
                Preference(
                    "organic",
                    False,
                    PreferenceSource.DEFAULT,
                    domain=settings.domain,
                ),
            ),
        )
        _runtime = ToolRuntime(
            context_service=context_service,
            memory_service=memory_service,
            agent_id=settings.app_name,
            domain=settings.domain,
        )
    return _runtime


def _identity(tool_context: Any) -> tuple[str, str]:
    # ADK Web and Agent Runtime own session creation, so use the native
    # invocation identity. The state fallback preserves compatibility with
    # older callers and lightweight unit-test contexts.
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
    """Get the centrally resolved preferences. Call before grocery recommendations or diagnostics."""
    runtime = _configured()
    user_id, session_id = _identity(tool_context)
    context = await runtime.context_service.build_context(
        user_id, session_id, runtime.agent_id, runtime.domain, session_state=tool_context.state
    )
    return context.to_dict()


def set_session_preference(key: str, value: Any, tool_context: Any) -> dict[str, Any]:
    """Set an explicitly temporary preference for only this session."""
    runtime = _configured()
    if key not in _ALLOWED_KEYS:
        return {"status": "rejected", "reason": "unsupported preference key"}
    state_key = f"preferences:{runtime.domain}"
    existing = tool_context.state.get(state_key, {})
    updated = dict(existing) if isinstance(existing, dict) else {}
    updated[key] = {"value": value, "updated_at": datetime.now(UTC).isoformat()}
    # Assignment is intentional: ADK records this as an event state_delta, unlike
    # mutating an untracked nested object in place.
    tool_context.state[state_key] = updated
    return {"status": "stored_in_session", "key": key, "memory_bank_written": False}


async def process_preference_statement(message: str, tool_context: Any) -> dict[str, Any]:
    """Classify an explicit preference statement and route by requested scope."""
    runtime = _configured()
    candidate = extract_candidate(message, runtime.domain)
    if candidate is None or candidate.key not in _ALLOWED_KEYS:
        return {"status": "no_candidate"}
    if candidate.requested_scope is PreferenceScope.SESSION:
        result = set_session_preference(candidate.key, candidate.value, tool_context)
        return {**result, "candidate": candidate.to_dict()}
    user_id, _ = _identity(tool_context)
    try:
        memory_name = await runtime.memory_service.promote_candidate(
            user_id, runtime.agent_id, candidate
        )
    except MemoryBankNotConfiguredError:
        return {
            "status": "not_persisted",
            "reason": "memory_bank_not_configured",
            "candidate": candidate.to_dict(),
            "memory_bank_written": False,
            "message": (
                "Long-term preference candidate recognized, but it was not saved "
                "because Agent Platform Memory Bank is not configured."
            ),
        }
    return {
        "status": "promoted_to_memory_bank",
        "candidate": candidate.to_dict(),
        "memory_name": memory_name,
    }
