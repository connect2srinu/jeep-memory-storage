from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from memory_api.domain.memory import (
    GenerationResult,
    MemoryEvent,
    MemoryProfile,
    MemoryProfileSchema,
    MemoryScope,
    NaturalMemory,
)


class MemoryBankClient(Protocol):
    """Small synchronous SDK seam; production calls are moved off the event loop."""

    def retrieve_profiles(self, *, scope: dict[str, str]) -> Any: ...

    def retrieve(self, *, scope: dict[str, str]) -> list[Any]: ...

    def create(self, *, fact: str, scope: dict[str, str]) -> Any: ...

    def ingest_event(self, *, text: str, scope: dict[str, str], stream_id: str) -> Any: ...


class AgentPlatformMemoryBankClient:
    def __init__(self, *, project: str, location: str, resource_id: str) -> None:
        import agentplatform

        client = agentplatform.Client(project=project, location=location)
        self._memories = client.agent_engines.memories
        self._name = f"projects/{project}/locations/{location}/reasoningEngines/{resource_id}"

    def retrieve_profiles(self, *, scope: dict[str, str]) -> Any:
        return self._memories.retrieve_profiles(name=self._name, scope=scope)

    def retrieve(self, *, scope: dict[str, str]) -> list[Any]:
        return list(self._memories.retrieve(name=self._name, scope=scope))

    def create(self, *, fact: str, scope: dict[str, str]) -> Any:
        return self._memories.create(name=self._name, fact=fact, scope=scope)

    def ingest_event(self, *, text: str, scope: dict[str, str], stream_id: str) -> Any:
        return self._memories.ingest_events(
            name=self._name,
            scope=scope,
            stream_id=stream_id,
            direct_contents_source={
                "events": [{"content": {"role": "user", "parts": [{"text": text}]}}]
            },
            # An omitted generation_rule force-flushes immediately in the current SDK.
            generation_trigger_config={},
        )


class VertexMemoryBankStore:
    """MemoryStore backed by Gemini Enterprise Agent Platform Memory Bank.

    Memory Profiles are read with ``retrieve_profiles``. The provider currently has no
    direct field-level profile update API, so explicit writes are persisted as typed,
    exact-scope memories and overlaid on retrieved profiles. Interaction events are also
    sent to ``ingest_events`` so configured provider profile generation remains lazy.
    """

    _EXPLICIT_SCHEMA = "shared-memory-explicit-preference/v1"
    _EVENT_SCHEMA = "shared-memory-event/v1"

    def __init__(self, client: MemoryBankClient) -> None:
        self._client = client
        self._schemas: dict[str, MemoryProfileSchema] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, *, project: str, location: str, resource_id: str) -> VertexMemoryBankStore:
        if not project.strip() or not resource_id.strip():
            raise ValueError("Vertex backend requires GOOGLE_CLOUD_PROJECT and AGENT_PLATFORM_MEMORY_BANK_ID")
        return cls(
            AgentPlatformMemoryBankClient(
                project=project,
                location=location,
                resource_id=resource_id,
            )
        )

    async def register_schema(self, schema: MemoryProfileSchema) -> None:
        if not schema.id.strip() or not schema.domain.strip() or not schema.fields:
            raise ValueError("schema id, domain, and fields are required")
        current = self._schemas.get(schema.id)
        if current is not None and current != schema:
            raise ValueError(f"schema {schema.id!r} is already registered differently")
        self._schemas[schema.id] = schema

    async def list_schemas(self, domains: tuple[str, ...]) -> tuple[MemoryProfileSchema, ...]:
        allowed = set(domains)
        return tuple(
            item
            for item in sorted(self._schemas.values(), key=lambda value: value.id)
            if item.domain in allowed
        )

    async def get_profiles(
        self, scope: MemoryScope, schema_ids: tuple[str, ...]
    ) -> tuple[MemoryProfile, ...]:
        for schema_id in schema_ids:
            self._require_schema_for_scope(schema_id, scope)
        raw_profiles, raw_memories = await asyncio.gather(
            asyncio.to_thread(self._client.retrieve_profiles, scope=self._scope(scope)),
            asyncio.to_thread(self._client.retrieve, scope=self._scope(scope)),
        )
        profiles = self._adapt_profiles(scope, raw_profiles, schema_ids)
        overlays = self._explicit_overlays(scope, raw_memories, schema_ids)
        by_schema = {profile.schema_id: profile for profile in profiles}
        for overlay in overlays:
            current = by_schema.get(overlay.schema_id)
            if current is None:
                by_schema[overlay.schema_id] = overlay
            else:
                by_schema[overlay.schema_id] = MemoryProfile(
                    schema_id=current.schema_id,
                    scope=scope,
                    values={**current.values, **overlay.values},
                    version=max(current.version, overlay.version),
                    updated_at=max(current.updated_at, overlay.updated_at),
                )
        return tuple(by_schema[item] for item in schema_ids if item in by_schema)

    async def get_natural_memories(self, scope: MemoryScope) -> tuple[NaturalMemory, ...]:
        items = await asyncio.to_thread(self._client.retrieve, scope=self._scope(scope))
        result = []
        for item in items:
            memory = getattr(item, "memory", item)
            fact = getattr(memory, "fact", None)
            payload = self._json_object(fact)
            if payload and payload.get("schema") == self._EVENT_SCHEMA:
                text = str(payload.get("text", ""))
            elif payload and payload.get("schema") == self._EXPLICIT_SCHEMA:
                continue
            elif isinstance(fact, str):
                text = fact
            else:
                continue
            result.append(
                NaturalMemory(
                    id=str(getattr(memory, "name", f"memory-{uuid4()}")),
                    scope=scope,
                    text=text,
                    created_at=self._timestamp(memory),
                )
            )
        return tuple(result)

    async def ingest_event(self, scope: MemoryScope, event: MemoryEvent) -> GenerationResult:
        if not event.text.strip():
            raise ValueError("event text must be non-empty")
        updated = []
        for candidate in event.candidates:
            updated.append(
                await self.write_preference(
                    scope,
                    schema_id=candidate.schema_id,
                    attribute=candidate.attribute,
                    value=candidate.value,
                )
            )
        event_payload = json.dumps(
            {"schema": self._EVENT_SCHEMA, "text": event.text},
            sort_keys=True,
            separators=(",", ":"),
        )
        created, _ = await asyncio.gather(
            asyncio.to_thread(self._client.create, fact=event_payload, scope=self._scope(scope)),
            asyncio.to_thread(
                self._client.ingest_event,
                text=event.text,
                scope=self._scope(scope),
                stream_id=f"{scope.organization_id}-{scope.user_id}",
            ),
        )
        natural = NaturalMemory(
            id=self._operation_reference(created),
            scope=scope,
            text=event.text,
            created_at=event.occurred_at,
        )
        return GenerationResult(natural_memory=natural, updated_profiles=tuple(updated))

    async def write_preference(
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
        async with self._lock:
            memories = await asyncio.to_thread(self._client.retrieve, scope=self._scope(scope))
            overlays = self._explicit_overlays(scope, memories, (schema_id,))
            current = next((item for item in overlays if item.schema_id == schema_id), None)
            version = (current.version if current else 0) + 1
            now = datetime.now(UTC)
            fact = json.dumps(
                {
                    "schema": self._EXPLICIT_SCHEMA,
                    "schema_id": schema_id,
                    "schema_version": schema.version,
                    "domain": schema.domain,
                    "attribute": attribute,
                    "value": value,
                    "version": version,
                    "updated_at": now.isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            await asyncio.to_thread(self._client.create, fact=fact, scope=self._scope(scope))
        values = dict(current.values) if current else {}
        values[attribute] = value
        return MemoryProfile(
            schema_id=schema_id,
            scope=scope,
            values=values,
            version=version,
            updated_at=now,
        )

    def _adapt_profiles(
        self, scope: MemoryScope, response: Any, schema_ids: tuple[str, ...]
    ) -> tuple[MemoryProfile, ...]:
        profiles = getattr(response, "profiles", {}) or {}
        result = []
        for raw_schema_id, raw_profile in profiles.items():
            schema_id = str(raw_schema_id)
            if schema_id not in schema_ids:
                continue
            schema = self._require_schema_for_scope(schema_id, scope)
            values = getattr(raw_profile, "profile", raw_profile)
            if not isinstance(values, dict):
                continue
            result.append(
                MemoryProfile(
                    schema_id=schema_id,
                    scope=scope,
                    values={key: value for key, value in values.items() if key in schema.fields},
                    updated_at=self._timestamp(raw_profile),
                )
            )
        return tuple(result)

    def _explicit_overlays(
        self, scope: MemoryScope, items: list[Any], schema_ids: tuple[str, ...]
    ) -> tuple[MemoryProfile, ...]:
        by_schema: dict[str, dict[str, Any]] = {}
        versions: dict[str, int] = {}
        timestamps: dict[str, datetime] = {}
        for item in items:
            memory = getattr(item, "memory", item)
            payload = self._json_object(getattr(memory, "fact", None))
            if not payload or payload.get("schema") != self._EXPLICIT_SCHEMA:
                continue
            schema_id = str(payload.get("schema_id", ""))
            if schema_id not in schema_ids:
                continue
            schema = self._require_schema_for_scope(schema_id, scope)
            if payload.get("domain") != schema.domain:
                continue
            attribute = str(payload.get("attribute", ""))
            if attribute not in schema.fields:
                continue
            version = int(payload.get("version", 1))
            if version < versions.get(schema_id, 0):
                continue
            by_schema.setdefault(schema_id, {})[attribute] = payload.get("value")
            versions[schema_id] = max(version, versions.get(schema_id, 0))
            timestamps[schema_id] = self._timestamp(memory, payload.get("updated_at"))
        return tuple(
            MemoryProfile(
                schema_id=schema_id,
                scope=scope,
                values=values,
                version=versions[schema_id],
                updated_at=timestamps[schema_id],
            )
            for schema_id, values in by_schema.items()
        )

    def _require_schema_for_scope(
        self, schema_id: str, scope: MemoryScope
    ) -> MemoryProfileSchema:
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise KeyError(f"unknown profile schema {schema_id!r}")
        return schema

    @staticmethod
    def _scope(scope: MemoryScope) -> dict[str, str]:
        return {"organization_id": scope.organization_id, "user_id": scope.user_id}

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, str):
            return None
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _timestamp(value: Any, fallback: Any = None) -> datetime:
        timestamp = getattr(value, "update_time", None) or getattr(value, "create_time", None)
        if isinstance(timestamp, datetime):
            return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        if isinstance(fallback, str):
            try:
                parsed = datetime.fromisoformat(fallback)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(UTC)

    @staticmethod
    def _operation_reference(operation: Any) -> str:
        response = getattr(operation, "response", None)
        return str(getattr(response, "name", None) or getattr(operation, "name", "accepted"))
