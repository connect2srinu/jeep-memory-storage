from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .models import Preference, PreferenceScope, PreferenceSource

SESSION_STATE_KEY = "preferences:customer.grocery"


def normalize_session_state(state: Mapping[str, Any], domain: str) -> list[Preference]:
    raw = state.get(f"preferences:{domain}", {})
    if not isinstance(raw, Mapping):
        return []
    result: list[Preference] = []
    for key, item in raw.items():
        if not isinstance(key, str):
            continue
        payload = item if isinstance(item, Mapping) else {"value": item}
        updated_at = payload.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        result.append(
            Preference(
                key=key,
                value=payload.get("value"),
                source=PreferenceSource.SESSION_OVERRIDE,
                scope=PreferenceScope.SESSION,
                domain=domain,
                confidence=1.0,
                updated_at=updated_at or datetime.now(UTC),
                provenance={"service": "agent-platform-session-state"},
            )
        )
    return result


class SessionPreferenceStore(ABC):
    @abstractmethod
    async def get_preferences(
        self, user_id: str, session_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        pass


class VertexAiSessionPreferenceStore(SessionPreferenceStore):
    """Reads structured state persisted by ADK's VertexAiSessionService."""

    def __init__(self, session_service: Any, app_name: str) -> None:
        self._session_service = session_service
        self._app_name = app_name

    async def get_preferences(
        self, user_id: str, session_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        session = await self._session_service.get_session(
            app_name=self._app_name, user_id=user_id, session_id=session_id
        )
        if session is None:
            return []
        return normalize_session_state(session.state, domain)
