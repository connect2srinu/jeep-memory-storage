from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Protocol
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


class MemoryBankClient(Protocol):
    """Small synchronous SDK seam; production calls are moved off the event loop."""

    def retrieve_profiles(self, *, scope: dict[str, str]) -> Any: ...

    def retrieve(self, *, scope: dict[str, str]) -> list[Any]: ...

    def create(self, *, fact: str, scope: dict[str, str]) -> Any: ...

    def ingest_event(self, *, text: str, scope: dict[str, str], stream_id: str) -> Any: ...

    def delete(self, *, name: str) -> Any: ...

    def list_memories(self) -> list[Any]: ...


class AgentPlatformMemoryBankClient:
    def __init__(self, *, project: str, location: str, resource_id: str) -> None:
        import agentplatform

        client = agentplatform.Client(project=project, location=location)
        # agentplatform 2.x exposes memory operations under ``memory_banks`` (with the
        # per-scope reads/writes under ``memory_banks.memories``); the 1.x ``agent_engines``
        # accessor was removed.
        self._banks = client.memory_banks
        self._memories = client.memory_banks.memories
        self._name = f"projects/{project}/locations/{location}/reasoningEngines/{resource_id}"

    def retrieve_profiles(self, *, scope: dict[str, str]) -> Any:
        return self._memories.retrieve_profiles(name=self._name, scope=scope)

    def retrieve(self, *, scope: dict[str, str]) -> list[Any]:
        return list(self._memories.retrieve(name=self._name, scope=scope))

    def create(self, *, fact: str, scope: dict[str, str]) -> Any:
        return self._memories.create(name=self._name, fact=fact, scope=scope)

    def ingest_event(self, *, text: str, scope: dict[str, str], stream_id: str) -> Any:
        return self._banks.ingest_events(
            name=self._name,
            scope=scope,
            stream_id=stream_id,
            direct_contents_source={
                "events": [{"content": {"role": "user", "parts": [{"text": text}]}}]
            },
            # An omitted generation_rule force-flushes immediately in the current SDK.
            generation_trigger_config={},
        )

    def delete(self, *, name: str) -> Any:
        return self._memories.delete(name=name)

    def list_memories(self) -> list[Any]:
        return list(self._memories.list(name=self._name))


class VertexMemoryBankStore:
    """MemoryStore backed by Gemini Enterprise Agent Platform Memory Bank.

    Memory Profiles are read with ``retrieve_profiles``. The provider currently has no
    direct field-level profile update API, so explicit writes are persisted as typed,
    exact-scope memories and overlaid on retrieved profiles. Interaction events are also
    sent to ``ingest_events`` so configured provider profile generation remains lazy.
    """

    _EXPLICIT_SCHEMA = "shared-memory-explicit-preference/v1"
    _EVENT_SCHEMA = "shared-memory-event/v1"
    _DYNAMIC_SCHEMA = "shared-memory-dynamic/v1"

    def __init__(self, client: MemoryBankClient) -> None:
        self._client = client
        self._schemas: dict[str, MemoryProfileSchema] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, *, project: str, location: str, resource_id: str) -> VertexMemoryBankStore:
        if not project.strip() or not resource_id.strip():
            raise ValueError(
                "Vertex backend requires GOOGLE_CLOUD_PROJECT and AGENT_PLATFORM_MEMORY_BANK_ID"
            )
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
        # A new schema version replaces the old one; the same version defined twice is an error.
        if current is not None and current != schema and current.version == schema.version:
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
        # Managed generation is intentionally NOT triggered: the provider's GenerateMemories would
        # extract arbitrary, ungoverned memories. Only explicit typed writes (canonical candidates
        # above, and topic-gated dynamic memories via write_dynamic_memory) are persisted, so the
        # control plane remains the sole authority over what is retained.
        created = await asyncio.to_thread(
            self._client.create, fact=event_payload, scope=self._scope(scope)
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
            memories = await asyncio.to_thread(self._client.retrieve, scope=self._scope(scope))
            current = self._dynamic_overlays(scope, memories, (topic,)).get(topic)
            version = (current.version if current else 0) + 1
            now = datetime.now(UTC)
            fact = json.dumps(
                {
                    "schema": self._DYNAMIC_SCHEMA,
                    "topic": topic,
                    "value": value,
                    "confidence": confidence,
                    "version": version,
                    "updated_at": now.isoformat(),
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "sensitivity": sensitivity,
                    "source": source,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            await asyncio.to_thread(self._client.create, fact=fact, scope=self._scope(scope))
        return DynamicMemory(
            scope=scope,
            topic=topic,
            value=value,
            confidence=confidence,
            version=version,
            updated_at=now,
            expires_at=expires_at,
            sensitivity=sensitivity,
            source=source,
        )

    async def get_dynamic_memories(
        self, scope: MemoryScope, topics: tuple[str, ...]
    ) -> tuple[DynamicMemory, ...]:
        memories = await asyncio.to_thread(self._client.retrieve, scope=self._scope(scope))
        overlays = self._dynamic_overlays(scope, memories, tuple(topics))
        return tuple(overlays[topic] for topic in sorted(overlays))

    async def forget_user(self, scope: MemoryScope) -> int:
        """Delete every memory for a user scope (right-to-be-forgotten). Returns count deleted.

        Uses ``list`` (authoritative enumeration) rather than ``retrieve`` (similarity retrieval,
        which does not reliably surface every memory) filtered by the memory's immutable scope.
        """
        items = await asyncio.to_thread(self._client.list_memories)
        names = []
        # A forget matches every memory whose scope contains all of the target scope's keys: a
        # broader scope cascades (e.g. household forget removes all members), a more specific scope
        # (e.g. household + member) targets just that partition.
        target = scope.as_dict()
        for item in items:
            memory = getattr(item, "memory", item)
            memory_scope = getattr(memory, "scope", None) or {}
            if any(memory_scope.get(key) != value for key, value in target.items()):
                continue
            name = getattr(memory, "name", None)
            if name:
                names.append(name)
        for name in names:
            await asyncio.to_thread(self._client.delete, name=name)
        return len(names)

    async def delete_preference(
        self, scope: MemoryScope, *, schema_id: str, attribute: str
    ) -> int:
        """Delete every version of one canonical attribute in exactly this scope (no cascade)."""
        target = scope.as_dict()
        items = await asyncio.to_thread(self._client.list_memories)
        names = []
        for item in items:
            memory = getattr(item, "memory", item)
            if dict(getattr(memory, "scope", None) or {}) != target:
                continue
            payload = self._json_object(getattr(memory, "fact", None))
            if (
                payload
                and payload.get("schema") == self._EXPLICIT_SCHEMA
                and payload.get("schema_id") == schema_id
                and payload.get("attribute") == attribute
                and getattr(memory, "name", None)
            ):
                names.append(memory.name)
        for name in names:
            await asyncio.to_thread(self._client.delete, name=name)
        return 1 if names else 0

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
    ) -> tuple[dict[str, Any], ...]:
        """Delete memories across the organization matching a filter (operator on-demand).

        ``dry_run`` returns the matches without deleting. Org isolation is enforced via each
        memory's immutable scope. ``schema_id`` / ``older_than`` restrict to canonical values of
        one schema last written before a time (retention).
        """
        items = await asyncio.to_thread(self._client.list_memories)
        # An attribute's value is its newest version; retention judges that version's time, and
        # deletes every stored version of an expired attribute.
        latest: dict[tuple[tuple[tuple[str, str], ...], str, str], datetime] = {}
        if older_than is not None:
            for item in items:
                memory = getattr(item, "memory", item)
                payload = self._json_object(getattr(memory, "fact", None))
                if not payload or payload.get("schema") != self._EXPLICIT_SCHEMA:
                    continue
                key = (
                    tuple(sorted((getattr(memory, "scope", None) or {}).items())),
                    str(payload.get("schema_id", "")),
                    str(payload.get("attribute", "")),
                )
                written = self._timestamp(memory, payload.get("updated_at"))
                latest[key] = max(latest.get(key, written), written)
        matches: list[dict[str, Any]] = []
        for item in items:
            memory = getattr(item, "memory", item)
            scope = getattr(memory, "scope", None) or {}
            if scope.get("organization_id") != organization_id:
                continue
            payload = self._json_object(getattr(memory, "fact", None))
            if not payload:
                continue
            if (schema_id or older_than) and payload.get("schema") != self._EXPLICIT_SCHEMA:
                continue
            if schema_id and payload.get("schema_id") != schema_id:
                continue
            if older_than is not None:
                key = (
                    tuple(sorted(scope.items())),
                    str(payload.get("schema_id", "")),
                    str(payload.get("attribute", "")),
                )
                if latest.get(key, older_than) >= older_than:
                    continue
            entry = self._match_purge(payload, tier, attribute, topic)
            if entry is None:
                continue
            matches.append(
                {
                    **entry,
                    "organizationId": organization_id,
                    "userId": scope.get("user_id"),
                    "scope": [scope[key] for key in sorted(scope)],
                    "schemaId": payload.get("schema_id"),
                    "name": getattr(memory, "name", None),
                }
            )
        if not dry_run:
            for match in matches:
                if match.get("name"):
                    await asyncio.to_thread(self._client.delete, name=match["name"])
        return tuple({k: v for k, v in match.items() if k != "name"} for match in matches)

    @staticmethod
    def _match_purge(
        payload: dict[str, Any], tier: str | None, attribute: str | None, topic: str | None
    ) -> dict[str, Any] | None:
        schema = payload.get("schema")
        if schema == VertexMemoryBankStore._EXPLICIT_SCHEMA:
            m_tier, key = "canonical", str(payload.get("attribute", ""))
        elif schema == VertexMemoryBankStore._DYNAMIC_SCHEMA:
            m_tier, key = "dynamic", str(payload.get("topic", ""))
        else:
            return None
        if tier and m_tier != tier:
            return None
        if m_tier == "canonical":
            if topic:
                return None
            if attribute and not (attribute == key or attribute.endswith(f".{key}")):
                return None
            return {"tier": "canonical", "attribute": key}
        if attribute:
            return None
        if topic and topic != key:
            return None
        return {"tier": "dynamic", "topic": key}

    def _dynamic_overlays(
        self, scope: MemoryScope, items: list[Any], topics: tuple[str, ...]
    ) -> dict[str, DynamicMemory]:
        approved = set(topics)
        result: dict[str, DynamicMemory] = {}
        versions: dict[str, int] = {}
        for item in items:
            memory = getattr(item, "memory", item)
            payload = self._json_object(getattr(memory, "fact", None))
            if not payload or payload.get("schema") != self._DYNAMIC_SCHEMA:
                continue
            topic = str(payload.get("topic", ""))
            if topic not in approved:
                continue
            # Keep the highest version *per topic* — each memory carries one topic, so retrieval
            # order (newest-first from the provider) must not drop lower-versioned other topics.
            version = int(payload.get("version", 1))
            if version < versions.get(topic, 0):
                continue
            expires_raw = payload.get("expires_at")
            expires_at: datetime | None = None
            if isinstance(expires_raw, str):
                try:
                    parsed = datetime.fromisoformat(expires_raw)
                    expires_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
                except ValueError:
                    expires_at = None
            versions[topic] = version
            result[topic] = DynamicMemory(
                scope=scope,
                topic=topic,
                value=payload.get("value"),
                confidence=float(payload.get("confidence", 1.0)),
                version=version,
                updated_at=self._timestamp(memory, payload.get("updated_at")),
                expires_at=expires_at,
                sensitivity=payload.get("sensitivity"),
                source=payload.get("source"),
            )
        return result

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
        attribute_versions: dict[str, dict[str, int]] = {}
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
            # Versions are per-schema and monotonic, but each memory carries a single
            # attribute, so keep the highest version *per attribute* — comparing against a
            # schema-wide max would drop older attributes whenever a newer one was written.
            seen = attribute_versions.setdefault(schema_id, {})
            if version < seen.get(attribute, 0):
                continue
            seen[attribute] = version
            by_schema.setdefault(schema_id, {})[attribute] = payload.get("value")
            if version >= versions.get(schema_id, 0):
                versions[schema_id] = version
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

    def _require_schema_for_scope(self, schema_id: str, scope: MemoryScope) -> MemoryProfileSchema:
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise KeyError(f"unknown profile schema {schema_id!r}")
        return schema

    @staticmethod
    def _scope(scope: MemoryScope) -> dict[str, str]:
        return scope.as_dict()

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
