from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import Preference, PreferenceSource


class NullMemoryProfileAdapter:
    async def get_memory_profile_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        del user_id, app_name, domains
        return []


class AgentPlatformMemoryProfileAdapter:
    """GA Memory Profiles retrieval adapter using retrieve_profiles."""

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

    async def get_memory_profile_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        project = self.project or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = self.location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        resource_id = (
            self.agent_engine_id
            or os.getenv("AGENT_PLATFORM_MEMORY_BANK_ID")
            or os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
        )
        if not project or not resource_id:
            return []
        import agentplatform

        client = agentplatform.Client(project=project, location=location)
        name = f"projects/{project}/locations/{location}/reasoningEngines/{resource_id}"

        def retrieve(domain: str) -> Any:
            return client.agent_engines.memories.retrieve_profiles(
                name=name,
                scope={"user_id": user_id, "app_name": app_name, "domain": domain},
            )

        responses = await asyncio.gather(
            *(asyncio.to_thread(retrieve, domain) for domain in domains)
        )
        result: list[Preference] = []
        for domain, response in zip(domains, responses, strict=True):
            for schema_id, profile in (getattr(response, "profiles", {}) or {}).items():
                for raw_key, value in (getattr(profile, "profile", {}) or {}).items():
                    entry = self.catalog.lookup(str(raw_key), domain)
                    key = entry.key if entry else f"{domain}.{raw_key}"
                    result.append(
                        Preference(
                            key=key,
                            value=value,
                            source=PreferenceSource.MEMORY_PROFILE,
                            owner_domain=entry.owner_domain if entry else domain,
                            confidence=1.0,
                            updated_at=datetime.now(UTC),
                            confirmed=True,
                            canonical=bool(entry),
                            schema_version=entry.schema_version if entry else "1",
                            sensitivity=entry.sensitivity if entry else "normal",
                            provenance={
                                "service": "agent-platform-memory-profile",
                                "schema_id": str(schema_id),
                            },
                        )
                    )
        return result

