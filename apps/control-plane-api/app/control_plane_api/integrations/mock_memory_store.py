from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from control_plane_api.domain.memory import (
    DynamicMemory,
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
        # (identity, schema_id) -> field -> last write time (drives per-attribute retention).
        self._field_times: dict[tuple[tuple[str, str], str], dict[str, datetime]] = {}
        self._natural_memories: dict[tuple[str, str], list[NaturalMemory]] = {}
        self._dynamic: dict[tuple[str, str], dict[str, DynamicMemory]] = {}
        self._lock = asyncio.Lock()

    async def register_schema(self, schema: MemoryProfileSchema) -> None:
        if not schema.id.strip() or not schema.domain.strip() or not schema.fields:
            raise ValueError("schema id, domain, and fields are required")
        async with self._lock:
            current = self._schemas.get(schema.id)
            # A new schema version replaces the old one; the same version defined twice is an error.
            if current is not None and current != schema and current.version == schema.version:
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

    async def write_dynamic_memory(
        self,
        scope: MemoryScope,
        *,
        topic: str,
        value: object,
        confidence: float,
        expires_at: datetime | None = None,
        sensitivity: str | None = None,
        source: str | None = None,
    ) -> DynamicMemory:
        async with self._lock:
            current = self._dynamic.setdefault(scope.identity, {}).get(topic)
            memory = DynamicMemory(
                scope=scope,
                topic=topic,
                value=value,
                confidence=confidence,
                version=(current.version if current else 0) + 1,
                updated_at=datetime.now(UTC),
                expires_at=expires_at,
                sensitivity=sensitivity,
                source=source,
            )
            self._dynamic[scope.identity][topic] = memory
            return memory

    async def get_dynamic_memories(
        self, scope: MemoryScope, topics: tuple[str, ...]
    ) -> tuple[DynamicMemory, ...]:
        approved = set(topics)
        stored = self._dynamic.get(scope.identity, {})
        return tuple(
            memory for topic, memory in sorted(stored.items()) if topic in approved
        )

    async def forget_user(self, scope: MemoryScope) -> int:
        async with self._lock:
            identity = scope.identity
            removed = 0
            # A broader identity is a prefix of the narrower ones under it (e.g. household
            # (org, household) is a prefix of (org, household, member)), so a household forget
            # cascades to every member; a member identity matches only that member.
            for key in [key for key in self._profiles if key[0][: len(identity)] == identity]:
                removed += len(self._profiles[key].values)
                del self._profiles[key]
                self._field_times.pop(key, None)
            removed += len(self._dynamic.pop(identity, {}))
            removed += len(self._natural_memories.pop(identity, []))
            return removed

    async def delete_preference(
        self, scope: MemoryScope, *, schema_id: str, attribute: str
    ) -> int:
        async with self._lock:
            key = scope.identity, schema_id
            return self._drop_field(key, attribute)

    def _drop_field(self, key: tuple[tuple[str, str], str], field: str) -> int:
        profile = self._profiles.get(key)
        if profile is None or field not in profile.values:
            return 0
        remaining = {name: value for name, value in profile.values.items() if name != field}
        if remaining:
            self._profiles[key] = replace(profile, values=remaining)
        else:
            del self._profiles[key]
        self._field_times.get(key, {}).pop(field, None)
        return 1

    async def purge(
        self,
        *,
        organization_id: str,
        tier: str | None = None,
        attribute: str | None = None,
        topic: str | None = None,
        schema_id: str | None = None,
        older_than: datetime | None = None,
        dry_run: bool = False,
    ) -> tuple[dict[str, object], ...]:
        if attribute or schema_id or older_than:
            tiers = {"canonical"}
        elif topic:
            tiers = {"dynamic"}
        elif tier:
            tiers = {tier}
        else:
            tiers = {"canonical", "dynamic"}
        async with self._lock:
            matches: list[dict[str, object]] = []
            if "canonical" in tiers:
                for (identity, stored_schema), profile in list(self._profiles.items()):
                    if identity[0] != organization_id:
                        continue
                    if schema_id and stored_schema != schema_id:
                        continue
                    written = self._field_times.get((identity, stored_schema), {})
                    for field in list(profile.values):
                        if attribute and not (attribute == field or attribute.endswith(f".{field}")):
                            continue
                        if older_than and written.get(field, profile.updated_at) >= older_than:
                            continue
                        matches.append(
                            {
                                "organizationId": identity[0],
                                "userId": identity[1],
                                "scope": list(identity),
                                "schemaId": stored_schema,
                                "tier": "canonical",
                                "attribute": field,
                            }
                        )
                        if not dry_run:
                            self._drop_field((identity, stored_schema), field)
            if "dynamic" in tiers:
                for identity, topics in list(self._dynamic.items()):
                    if identity[0] != organization_id:
                        continue
                    for stored_topic in list(topics):
                        if topic and stored_topic != topic:
                            continue
                        matches.append(
                            {
                                "organizationId": identity[0],
                                "userId": identity[1],
                                "tier": "dynamic",
                                "topic": stored_topic,
                            }
                        )
                        if not dry_run:
                            del self._dynamic[identity][stored_topic]
            return tuple(matches)

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
        self._field_times.setdefault(key, {})[attribute] = profile.updated_at
        return profile

    def _require_schema_for_scope(self, schema_id: str, scope: MemoryScope) -> MemoryProfileSchema:
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise KeyError(f"unknown profile schema {schema_id!r}")
        return schema
