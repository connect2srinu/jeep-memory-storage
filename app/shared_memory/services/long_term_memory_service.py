from __future__ import annotations

from typing import Protocol

from app.shared_memory.models import Preference


class DynamicMemoryBackend(Protocol):
    async def get_dynamic_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]: ...

    async def store_dynamic_preference(
        self, user_id: str, app_name: str, preference: Preference
    ) -> str: ...


class MemoryProfileBackend(Protocol):
    async def get_memory_profile_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]: ...


class LongTermMemoryService:
    def __init__(
        self,
        dynamic_backend: DynamicMemoryBackend,
        profile_backend: MemoryProfileBackend,
    ) -> None:
        self.dynamic_backend = dynamic_backend
        self.profile_backend = profile_backend

    async def get_dynamic_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        return await self.dynamic_backend.get_dynamic_preferences(user_id, app_name, domains)

    async def get_memory_profile_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        return await self.profile_backend.get_memory_profile_preferences(
            user_id, app_name, domains
        )

    async def store_dynamic_preference(
        self, user_id: str, app_name: str, preference: Preference
    ) -> str:
        return await self.dynamic_backend.store_dynamic_preference(user_id, app_name, preference)

