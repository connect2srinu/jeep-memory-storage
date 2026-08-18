from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import Preference, PreferenceSource
from app.shared_memory.observability import log_event


def _load_profile_registry() -> dict[str, dict[str, Any]]:
    path = files("app.shared_memory.profiles").joinpath("memory_profiles.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    registry = payload.get("profile_registry", {})
    if not isinstance(registry, dict):
        return {}
    return {
        str(schema_id): metadata
        for schema_id, metadata in registry.items()
        if isinstance(metadata, dict)
    }


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
        profile_registry: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.catalog = catalog
        self.project = project
        self.location = location
        self.agent_engine_id = agent_engine_id
        self.profile_registry = (
            _load_profile_registry() if profile_registry is None else profile_registry
        )

    def _reject_profile_value(
        self,
        *,
        requested_domain: str,
        schema_id: str,
        raw_key: str | None,
        reason: str,
    ) -> None:
        log_event(
            "memory_profile_value_rejected",
            requested_domain=requested_domain,
            schema_id=schema_id,
            profile_field=raw_key,
            reason=reason,
        )

    def _normalize_response(self, domain: str, response: Any) -> list[Preference]:
        result: list[Preference] = []
        profiles = getattr(response, "profiles", {}) or {}
        for raw_schema_id, profile in profiles.items():
            schema_id = str(raw_schema_id)
            metadata = self.profile_registry.get(schema_id)
            if metadata is None:
                self._reject_profile_value(
                    requested_domain=domain,
                    schema_id=schema_id,
                    raw_key=None,
                    reason="UNKNOWN_SCHEMA",
                )
                continue

            schema_owner = str(metadata.get("owner_domain", ""))
            if schema_owner != domain:
                self._reject_profile_value(
                    requested_domain=domain,
                    schema_id=schema_id,
                    raw_key=None,
                    reason="SCHEMA_OWNER_MISMATCH",
                )
                continue

            field_mappings = metadata.get("fields", {})
            if not isinstance(field_mappings, dict):
                self._reject_profile_value(
                    requested_domain=domain,
                    schema_id=schema_id,
                    raw_key=None,
                    reason="INVALID_SCHEMA_REGISTRY",
                )
                continue

            values = getattr(profile, "profile", {}) or {}
            for raw_key, value in values.items():
                profile_field = str(raw_key)
                canonical_key = field_mappings.get(profile_field)
                if not isinstance(canonical_key, str):
                    self._reject_profile_value(
                        requested_domain=domain,
                        schema_id=schema_id,
                        raw_key=profile_field,
                        reason="UNKNOWN_PROFILE_FIELD",
                    )
                    continue

                entry = self.catalog.lookup(canonical_key)
                if entry is None or entry.owner_domain != schema_owner:
                    self._reject_profile_value(
                        requested_domain=domain,
                        schema_id=schema_id,
                        raw_key=profile_field,
                        reason="CATALOG_OWNER_MISMATCH",
                    )
                    continue

                result.append(
                    Preference(
                        key=entry.key,
                        value=value,
                        source=PreferenceSource.MEMORY_PROFILE,
                        owner_domain=entry.owner_domain,
                        confidence=1.0,
                        updated_at=datetime.now(UTC),
                        confirmed=True,
                        canonical=True,
                        schema_version=entry.schema_version,
                        sensitivity=entry.sensitivity,
                        provenance={
                            "service": "agent-platform-memory-profile",
                            "schema_id": schema_id,
                        },
                    )
                )
        return result

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
            result.extend(self._normalize_response(domain, response))
        return result
