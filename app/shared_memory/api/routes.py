from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from app.shared_memory.models import PreferenceCandidate, PreferenceScope
from app.shared_memory.services import SharedMemoryPlatformService


class ResolveContextRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    session_id: str = Field(alias="sessionId")
    consumer_domain: str = Field(alias="consumerDomain")
    agent_id: str = Field(alias="agentId")
    context: dict[str, Any] = Field(default_factory=dict)


class SubmitPreferenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    session_id: str = Field(alias="sessionId")
    consumer_domain: str = Field(alias="consumerDomain")
    agent_id: str = Field(alias="agentId")
    key: str
    value: Any
    proposed_domain: str = Field(alias="proposedDomain")
    requested_scope: PreferenceScope = Field(alias="requestedScope")
    confidence: float = 1.0
    source: str = "API"
    source_message: str = Field(default="", alias="sourceMessage")
    explicit: bool = True


def create_api_app(platform: SharedMemoryPlatformService) -> FastAPI:
    api = FastAPI(
        title="Shared Memory Platform API",
        version="1.0.0",
        description="Domain-authorized preference resolution and submission service.",
    )

    @api.post("/v1/memory/context/resolve")
    async def resolve_context(request: ResolveContextRequest) -> dict[str, Any]:
        context = await platform.get_effective_context(
            user_id=request.user_id,
            session_id=request.session_id,
            consumer_domain=request.consumer_domain,
            agent_id=request.agent_id,
            context=request.context,
        )
        return context.to_dict()

    @api.post("/v1/memory/preferences")
    async def submit_preference(request: SubmitPreferenceRequest) -> dict[str, Any]:
        candidate = PreferenceCandidate(
            key=request.key,
            value=request.value,
            proposed_domain=request.proposed_domain,
            requested_scope=request.requested_scope,
            confidence=request.confidence,
            source=request.source,
            source_message=request.source_message,
            user_id=request.user_id,
            session_id=request.session_id,
            explicit=request.explicit,
            evidence="submitted through Shared Memory Platform API",
        )
        result = await platform.submit_preference(
            candidate=candidate,
            consumer_domain=request.consumer_domain,
            agent_id=request.agent_id,
        )
        return result.to_dict()

    @api.get("/v1/memory/users/{user_id}/effective-context")
    async def get_effective_context(
        user_id: str,
        consumer_domain: str = Query(alias="consumerDomain"),
        agent_id: str = Query(alias="agentId"),
        session_id: str = Query(alias="sessionId"),
    ) -> dict[str, Any]:
        context = await platform.get_effective_context(
            user_id=user_id,
            session_id=session_id,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
        )
        return context.to_dict()

    return api

