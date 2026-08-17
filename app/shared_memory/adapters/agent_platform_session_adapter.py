from __future__ import annotations

import asyncio
from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime
from typing import Any

from app.shared_memory.models import Preference, PreferenceScope, PreferenceSource

STATE_KEY = "shared_memory:preferences"


def normalize_structured_state(state: Mapping[str, Any]) -> list[Preference]:
    """Read structured preference state only; conversation events are intentionally ignored."""
    raw = state.get(STATE_KEY, {})
    if not isinstance(raw, Mapping):
        return []
    result: list[Preference] = []
    for key, item in raw.items():
        if not isinstance(key, str) or not isinstance(item, Mapping):
            continue
        owner_domain = str(item.get("owner_domain") or key.split(".", 1)[0])
        updated_at = item.get("updated_at")
        expires_at = item.get("expires_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        result.append(
            Preference(
                key=key,
                value=item.get("value"),
                source=PreferenceSource.SESSION_OVERRIDE,
                owner_domain=owner_domain,
                scope=PreferenceScope.SESSION,
                confidence=1.0,
                updated_at=updated_at or datetime.now(UTC),
                expires_at=expires_at,
                canonical=bool(item.get("canonical", False)),
                schema_version=str(item.get("schema_version", "1")),
                sensitivity=str(item.get("sensitivity", "normal")),
                provenance={"service": "agent-platform-session-state"},
            )
        )
    return result


def write_structured_state(state: MutableMapping[str, Any], preference: Preference) -> None:
    raw = state.get(STATE_KEY, {})
    updated = dict(raw) if isinstance(raw, Mapping) else {}
    updated[preference.key] = {
        "value": preference.value,
        "owner_domain": preference.owner_domain,
        "updated_at": (preference.updated_at or datetime.now(UTC)).isoformat(),
        "expires_at": preference.expires_at.isoformat() if preference.expires_at else None,
        "canonical": preference.canonical,
        "schema_version": preference.schema_version,
        "sensitivity": preference.sensitivity,
    }
    # Top-level assignment is required for ADK to emit an event state_delta.
    state[STATE_KEY] = updated


class ToolContextSessionAdapter:
    def __init__(self, tool_context: Any) -> None:
        self.tool_context = tool_context

    async def get_session_preferences(
        self, user_id: str, session_id: str, readable_domains: tuple[str, ...]
    ) -> list[Preference]:
        del user_id, session_id
        return [
            preference
            for preference in normalize_structured_state(self.tool_context.state)
            if preference.owner_domain in readable_domains
        ]

    async def save_session_preference(
        self, user_id: str, session_id: str, preference: Preference
    ) -> None:
        del user_id, session_id
        write_structured_state(self.tool_context.state, preference)


class InMemorySessionAdapter:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], dict[str, Any]] = {}

    async def get_session_preferences(
        self, user_id: str, session_id: str, readable_domains: tuple[str, ...]
    ) -> list[Preference]:
        state = self._states.get((user_id, session_id), {})
        return [
            preference
            for preference in normalize_structured_state(state)
            if preference.owner_domain in readable_domains
        ]

    async def save_session_preference(
        self, user_id: str, session_id: str, preference: Preference
    ) -> None:
        state = self._states.setdefault((user_id, session_id), {})
        write_structured_state(state, preference)

    def state(self, user_id: str, session_id: str) -> dict[str, Any]:
        return self._states.get((user_id, session_id), {})


class AgentPlatformSessionAdapter:
    """Supported Agent Platform client adapter for managed session reads.

    Session writes from an ADK invocation should use ToolContextSessionAdapter so ADK records
    state deltas. The Agent Platform Sessions surface currently exposes session/event operations,
    not an arbitrary out-of-band state patch in the SDK used by this POC.
    """

    def __init__(self, *, project: str, location: str, agent_engine_id: str) -> None:
        import agentplatform

        self._client = agentplatform.Client(project=project, location=location)
        self._engine_name = (
            f"projects/{project}/locations/{location}/reasoningEngines/{agent_engine_id}"
        )

    async def get_session_preferences(
        self, user_id: str, session_id: str, readable_domains: tuple[str, ...]
    ) -> list[Preference]:
        def get() -> Any:
            name = f"{self._engine_name}/sessions/{session_id}"
            return self._client.agent_engines.sessions.get(name=name)

        session = await asyncio.to_thread(get)
        if session.user_id != user_id:
            raise PermissionError("managed session does not belong to user")
        state = session.session_state or {}
        return [
            preference
            for preference in normalize_structured_state(state)
            if preference.owner_domain in readable_domains
        ]

    async def save_session_preference(
        self, user_id: str, session_id: str, preference: Preference
    ) -> None:
        del user_id, session_id, preference
        raise NotImplementedError(
            "Use ToolContextSessionAdapter during ADK invocations so writes become event state deltas"
        )

