from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import Preference, PreferenceScope, PreferenceSource


class MemoryBankNotConfiguredError(RuntimeError):
    pass


class AgentPlatformMemoryBankAdapter:
    """Dynamic-memory adapter using documented agentplatform.Client methods."""

    def __init__(
        self,
        catalog: PreferenceCatalog,
        *,
        project: str | None = None,
        location: str | None = None,
        agent_engine_id: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.project = project
        self.location = location
        self.agent_engine_id = agent_engine_id
        self._client: Any = None
        self._resource_name: str | None = None

    def _bind(self) -> tuple[Any, str]:
        if self._client is not None and self._resource_name is not None:
            return self._client, self._resource_name
        project = self.project or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = self.location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        resource_id = (
            self.agent_engine_id
            or os.getenv("AGENT_PLATFORM_MEMORY_BANK_ID")
            or os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
        )
        if not project or not resource_id:
            raise MemoryBankNotConfiguredError("Memory Bank is not configured")
        import agentplatform

        self._client = agentplatform.Client(project=project, location=location)
        self._resource_name = (
            f"projects/{project}/locations/{location}/reasoningEngines/{resource_id}"
        )
        return self._client, self._resource_name

    @staticmethod
    def _scope(user_id: str, app_name: str, domain: str) -> dict[str, str]:
        return {"user_id": user_id, "app_name": app_name, "domain": domain}

    async def get_dynamic_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        client, resource_name = self._bind()

        def retrieve(domain: str) -> list[Any]:
            return list(
                client.agent_engines.memories.retrieve(
                    name=resource_name,
                    scope=self._scope(user_id, app_name, domain),
                )
            )

        lookup_domains = [
            (requested_domain, scope_domain)
            for requested_domain in domains
            for scope_domain in (
                (requested_domain, "customer.grocery")
                if requested_domain == "grocery"
                else (requested_domain,)
            )
        ]
        pages = await asyncio.gather(
            *(asyncio.to_thread(retrieve, scope_domain) for _, scope_domain in lookup_domains)
        )
        result: list[Preference] = []
        for (domain, _), retrieved_items in zip(lookup_domains, pages, strict=True):
            for retrieved in retrieved_items:
                preference = self._adapt(retrieved, domain)
                if preference is not None:
                    result.append(preference)
        return result

    def _adapt(self, retrieved: Any, domain: str) -> Preference | None:
        memory = getattr(retrieved, "memory", retrieved)
        fact = getattr(memory, "fact", None)
        if not isinstance(fact, str):
            return None
        try:
            payload = json.loads(fact)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or "key" not in payload or "value" not in payload:
            return None
        owner_domain = str(payload.get("owner_domain") or payload.get("domain") or domain)
        if owner_domain == "customer.grocery":
            owner_domain = "grocery"
        if owner_domain != domain:
            return None
        raw_key = str(payload["key"])
        key, _, _ = self.catalog.canonicalize(raw_key, owner_domain)
        entry = self.catalog.lookup(key, owner_domain)
        source_name = payload.get("source")
        if source_name in PreferenceSource._value2member_map_:
            source = PreferenceSource(source_name)
        else:
            source = PreferenceSource.DOMAIN_MEMORY if entry else PreferenceSource.DYNAMIC_MEMORY
        confidence = payload.get("confidence")
        if confidence is None:
            distance = getattr(retrieved, "distance", None)
            confidence = 0.8 if distance is None else 1.0 / (1.0 + float(distance))
        return Preference(
            key=key,
            value=payload["value"],
            source=source,
            owner_domain=owner_domain,
            scope=PreferenceScope.LONG_TERM,
            confidence=float(confidence),
            updated_at=getattr(memory, "update_time", None),
            expires_at=getattr(memory, "expire_time", None),
            confirmed=bool(payload.get("confirmed", True)),
            canonical=bool(entry),
            schema_version=str(payload.get("schema_version", "1")),
            sensitivity=entry.sensitivity if entry else "normal",
            provenance={
                "service": "agent-platform-memory-bank",
                "memory_name": getattr(memory, "name", "unknown"),
            },
        )

    async def store_dynamic_preference(
        self, user_id: str, app_name: str, preference: Preference
    ) -> str:
        client, resource_name = self._bind()
        fact = json.dumps(
            {
                "schema": "shared-memory-preference/v2",
                "schema_version": preference.schema_version,
                "owner_domain": preference.owner_domain,
                "key": preference.key,
                "value": preference.value,
                "source": preference.source.value,
                "confidence": preference.confidence,
                "confirmed": preference.confirmed,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

        def create() -> Any:
            return client.agent_engines.memories.create(
                name=resource_name,
                fact=fact,
                scope=self._scope(user_id, app_name, preference.owner_domain),
            )

        operation = await asyncio.to_thread(create)
        response = getattr(operation, "response", None)
        return str(getattr(response, "name", getattr(operation, "name", "created")))


class InMemoryLongTermMemoryAdapter:
    def __init__(self, initial: list[tuple[str, str, Preference]] | None = None) -> None:
        self._items: list[tuple[str, str, Preference]] = list(initial or [])

    async def get_dynamic_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        return [
            preference
            for item_user, item_app, preference in self._items
            if item_user == user_id
            and item_app == app_name
            and preference.owner_domain in domains
        ]

    async def store_dynamic_preference(
        self, user_id: str, app_name: str, preference: Preference
    ) -> str:
        self._items.append((user_id, app_name, preference))
        return f"memory-{len(self._items)}"
