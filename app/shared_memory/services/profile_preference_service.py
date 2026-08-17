from __future__ import annotations

import asyncio
from typing import Protocol

from app.shared_memory.models import Preference


class ProfileAdapter(Protocol):
    async def get_preferences(
        self, user_id: str, domains: tuple[str, ...]
    ) -> list[Preference]: ...


class ProfilePreferenceService:
    """Composes replaceable authoritative profile adapters."""

    def __init__(self, adapters: tuple[ProfileAdapter, ...]) -> None:
        self.adapters = adapters

    async def get_preferences(
        self, user_id: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        if not self.adapters:
            return []
        results = await asyncio.gather(
            *(adapter.get_preferences(user_id, domains) for adapter in self.adapters)
        )
        return [preference for group in results for preference in group]

