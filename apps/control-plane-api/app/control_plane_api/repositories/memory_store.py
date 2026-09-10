from __future__ import annotations

from datetime import datetime
from typing import Protocol

from control_plane_api.domain.memory import (
    DynamicMemory,
    GenerationResult,
    MemoryEvent,
    MemoryProfile,
    MemoryProfileSchema,
    MemoryScope,
    NaturalMemory,
)


class MemoryStore(Protocol):
    async def register_schema(self, schema: MemoryProfileSchema) -> None: ...

    async def list_schemas(self, domains: tuple[str, ...]) -> tuple[MemoryProfileSchema, ...]: ...

    async def get_profiles(
        self, scope: MemoryScope, schema_ids: tuple[str, ...]
    ) -> tuple[MemoryProfile, ...]: ...

    async def get_natural_memories(self, scope: MemoryScope) -> tuple[NaturalMemory, ...]: ...

    async def ingest_event(self, scope: MemoryScope, event: MemoryEvent) -> GenerationResult: ...

    async def write_preference(
        self,
        scope: MemoryScope,
        *,
        schema_id: str,
        attribute: str,
        value: object,
    ) -> MemoryProfile: ...

    async def write_dynamic_memory(
        self,
        scope: MemoryScope,
        *,
        topic: str,
        value: object,
        confidence: float,
        expires_at: datetime | None = None,
    ) -> DynamicMemory: ...

    async def get_dynamic_memories(
        self, scope: MemoryScope, topics: tuple[str, ...]
    ) -> tuple[DynamicMemory, ...]: ...

    async def forget_user(self, scope: MemoryScope) -> int: ...

    async def purge(
        self,
        *,
        organization_id: str,
        tier: str | None = None,
        attribute: str | None = None,
        topic: str | None = None,
        dry_run: bool = False,
    ) -> tuple[dict[str, object], ...]: ...
