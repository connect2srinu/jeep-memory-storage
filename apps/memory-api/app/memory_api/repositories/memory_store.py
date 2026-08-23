from __future__ import annotations

from typing import Protocol

from memory_api.domain.memory import (
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
