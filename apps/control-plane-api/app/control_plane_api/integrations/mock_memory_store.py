from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from control_plane_api.domain.memory import (
    GenerationResult,
    MemoryEvent,
    MemoryProfile,
    MemoryProfileSchema,
    MemoryScope,
    NaturalMemory,
)


class MockMemoryStore:
    """Scope-aware deterministic backend used by local development and contract tests."""

    def __init__(self) -> None:
        self._schemas: dict[str, MemoryProfileSchema] = {}
        self._profiles: dict[tuple[tuple[str, str], str], MemoryProfile] = {}
        self._natural_memories: dict[tuple[str, str], list[NaturalMemory]] = {}
        self._lock = asyncio.Lock()

    async def register_schema(self, schema: MemoryProfileSchema) -> None:
        if not schema.id.strip() or not schema.domain.strip() or not schema.fields:
            raise ValueError("schema id, domain, and fields are required")
        async with self._lock:
            current = self._schemas.get(schema.id)
            if current is not None and current != schema:
                raise ValueError(f"schema {schema.id!r} is already registered differently")
            self._schemas[schema.id] = schema

    async def list_schemas(self, domains: tuple[str, ...]) -> tuple[MemoryProfileSchema, ...]:
        allowed = set(domains)
        return tuple(
            schema
            for schema in sorted(self._schemas.values(), key=lambda item: item.id)
            if schema.domain in allowed
        )

    async def get_profiles(
        self, scope: MemoryScope, schema_ids: tuple[str, ...]
    ) -> tuple[MemoryProfile, ...]:
        profiles = []
        for schema_id in schema_ids:
            self._require_schema_for_scope(schema_id, scope)
            profile = self._profiles.get((scope.identity, schema_id))
            if profile is not None:
                profiles.append(profile)
        return tuple(profiles)

    async def get_natural_memories(self, scope: MemoryScope) -> tuple[NaturalMemory, ...]:
        return tuple(self._natural_memories.get(scope.identity, ()))

    async def ingest_event(self, scope: MemoryScope, event: MemoryEvent) -> GenerationResult:
        if not event.text.strip():
            raise ValueError("event text must be non-empty")
        async with self._lock:
            natural = NaturalMemory(
                id=f"memory-{uuid4()}",
                scope=scope,
                text=event.text,
                created_at=event.occurred_at,
            )
            self._natural_memories.setdefault(scope.identity, []).append(natural)
            updated = tuple(
                self._write_unlocked(
                    scope,
                    schema_id=candidate.schema_id,
                    attribute=candidate.attribute,
                    value=candidate.value,
                )
                for candidate in event.candidates
            )
            return GenerationResult(natural_memory=natural, updated_profiles=updated)

    async def write_preference(
        self,
        scope: MemoryScope,
        *,
        schema_id: str,
        attribute: str,
        value: object,
    ) -> MemoryProfile:
        async with self._lock:
            return self._write_unlocked(
                scope,
                schema_id=schema_id,
                attribute=attribute,
                value=value,
            )

    def _write_unlocked(
        self,
        scope: MemoryScope,
        *,
        schema_id: str,
        attribute: str,
        value: object,
    ) -> MemoryProfile:
        schema = self._require_schema_for_scope(schema_id, scope)
        if attribute not in schema.fields:
            raise ValueError(f"attribute {attribute!r} is not in schema {schema_id!r}")
        key = scope.identity, schema_id
        current = self._profiles.get(key)
        if current is None:
            profile = MemoryProfile(schema_id=schema_id, scope=scope, values={attribute: value})
        else:
            values = {**current.values, attribute: value}
            profile = replace(
                current,
                values=values,
                version=current.version + 1,
                updated_at=datetime.now(UTC),
            )
        self._profiles[key] = profile
        return profile

    def _require_schema_for_scope(self, schema_id: str, scope: MemoryScope) -> MemoryProfileSchema:
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise KeyError(f"unknown profile schema {schema_id!r}")
        return schema
