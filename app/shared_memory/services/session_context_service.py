from __future__ import annotations

from typing import Protocol

from app.shared_memory.models import Preference


class SessionPreferenceBackend(Protocol):
    async def get_session_preferences(
        self, user_id: str, session_id: str, readable_domains: tuple[str, ...]
    ) -> list[Preference]: ...

    async def save_session_preference(
        self, user_id: str, session_id: str, preference: Preference
    ) -> None: ...


class SessionContextService:
    """Framework-neutral boundary for structured session preference state."""

    def __init__(self, backend: SessionPreferenceBackend) -> None:
        self.backend = backend

    async def get_session_preferences(
        self,
        user_id: str,
        session_id: str,
        readable_domains: tuple[str, ...],
    ) -> list[Preference]:
        return await self.backend.get_session_preferences(user_id, session_id, readable_domains)

    async def save_session_preference(
        self,
        user_id: str,
        session_id: str,
        preference: Preference,
    ) -> None:
        await self.backend.save_session_preference(user_id, session_id, preference)

