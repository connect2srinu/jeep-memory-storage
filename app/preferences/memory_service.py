from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from .memory_adapter import MemoryPreferenceAdapter
from .models import Preference, PreferenceCandidate, PreferenceSource


class MemoryBankNotConfiguredError(RuntimeError):
    """Raised when a Memory Bank operation is requested without a resource ID."""


class LongTermPreferenceService(ABC):
    @abstractmethod
    async def retrieve_preferences(
        self, user_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        pass

    @abstractmethod
    async def promote_candidate(
        self, user_id: str, agent_id: str, candidate: PreferenceCandidate
    ) -> str:
        pass


class VertexAiMemoryBankPreferenceService(LongTermPreferenceService):
    """Real Agent Platform Memory Bank adapter using the current Vertex AI client."""

    def __init__(self, *, project: str, location: str, agent_engine_id: str) -> None:
        try:
            import agentplatform
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Install google-cloud-aiplatform[agent_engines,adk]") from exc
        self._resource_name = (
            f"projects/{project}/locations/{location}/reasoningEngines/{agent_engine_id}"
        )
        self._client = agentplatform.Client(project=project, location=location)
        self._adapter = MemoryPreferenceAdapter()

    def _scope(self, user_id: str, agent_id: str, domain: str) -> dict[str, str]:
        return {"user_id": user_id, "app_name": agent_id, "domain": domain}

    async def retrieve_preferences(
        self, user_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        def retrieve() -> list[Any]:
            return list(
                self._client.agent_engines.memories.retrieve(
                    name=self._resource_name,
                    scope=self._scope(user_id, agent_id, domain),
                )
            )

        memories = await asyncio.to_thread(retrieve)
        return [
            preference for item in memories if (preference := self._adapter.adapt(item, domain))
        ]

    async def promote_candidate(
        self, user_id: str, agent_id: str, candidate: PreferenceCandidate
    ) -> str:
        preference = Preference(
            key=candidate.key,
            value=candidate.value,
            source=PreferenceSource.LONG_TERM_MEMORY,
            domain=candidate.domain,
            confidence=candidate.confidence,
            updated_at=datetime.now(UTC),
            provenance={"evidence": candidate.evidence},
        )

        def create() -> Any:
            return self._client.agent_engines.memories.create(
                name=self._resource_name,
                fact=self._adapter.encode_fact(preference),
                scope=self._scope(user_id, agent_id, candidate.domain),
            )

        operation = await asyncio.to_thread(create)
        return str(
            getattr(
                getattr(operation, "response", None), "name", getattr(operation, "name", "created")
            )
        )


class UnavailableMemoryService(LongTermPreferenceService):
    async def retrieve_preferences(
        self, user_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        raise MemoryBankNotConfiguredError("Memory Bank is not configured")

    async def promote_candidate(
        self, user_id: str, agent_id: str, candidate: PreferenceCandidate
    ) -> str:
        raise MemoryBankNotConfiguredError("Memory Bank is not configured")


class EnvironmentMemoryBankPreferenceService(LongTermPreferenceService):
    """Lazily bind after Agent Runtime injects its resource ID."""

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        agent_engine_id: str | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._agent_engine_id = agent_engine_id
        self._bound: VertexAiMemoryBankPreferenceService | None = None

    def _delegate(self) -> VertexAiMemoryBankPreferenceService:
        if self._bound is not None:
            return self._bound
        project = self._project or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = self._location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        agent_engine_id = (
            self._agent_engine_id
            or os.getenv("AGENT_PLATFORM_MEMORY_BANK_ID")
            or os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
        )
        if not project or not agent_engine_id:
            raise MemoryBankNotConfiguredError("Memory Bank is not configured")
        self._bound = VertexAiMemoryBankPreferenceService(
            project=project, location=location, agent_engine_id=agent_engine_id
        )
        return self._bound

    async def retrieve_preferences(
        self, user_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        return await self._delegate().retrieve_preferences(user_id, agent_id, domain)

    async def promote_candidate(
        self, user_id: str, agent_id: str, candidate: PreferenceCandidate
    ) -> str:
        return await self._delegate().promote_candidate(user_id, agent_id, candidate)
