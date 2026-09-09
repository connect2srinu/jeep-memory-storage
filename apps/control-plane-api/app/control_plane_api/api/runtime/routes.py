from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Depends, Request

from control_plane_api.api.runtime.models import (
    DynamicMemoryWrite,
    EffectivePreferenceSnapshotResponse,
    ExplicitPreferenceUpdate,
    MemoryEventRequest,
    RawProfilesRequest,
    ResolvePreferencesRequest,
    RuntimeMutationResponse,
)
from control_plane_api.security.authentication import AgentAuthenticator, AuthenticatedPrincipal
from control_plane_api.services.runtime_service import RuntimeMemoryService

ServiceDependency = Callable[[], AsyncIterator[RuntimeMemoryService]]


def create_runtime_router(
    *,
    authenticator: AgentAuthenticator,
    service_dependency: ServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])

    async def principal(request: Request) -> AuthenticatedPrincipal:
        return await authenticator.authenticate(request)

    @router.post("/preferences/resolve", response_model=EffectivePreferenceSnapshotResponse)
    async def resolve_preferences(
        payload: ResolvePreferencesRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> EffectivePreferenceSnapshotResponse:
        return await service.resolve_preferences(identity, payload)

    @router.post("/profiles")
    async def raw_profiles(
        payload: RawProfilesRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> dict[str, object]:
        return await service.raw_profiles(identity, payload)

    @router.post("/memory/events", response_model=RuntimeMutationResponse)
    async def ingest_event(
        payload: MemoryEventRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.ingest_event(identity, payload)

    @router.post("/memory/dynamic", response_model=RuntimeMutationResponse)
    async def write_dynamic_memory(
        payload: DynamicMemoryWrite,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.write_dynamic_memory(identity, payload)

    @router.put("/preferences/{attribute}", response_model=RuntimeMutationResponse)
    async def update_preference(
        attribute: str,
        payload: ExplicitPreferenceUpdate,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.update_preference(identity, attribute, payload)

    @router.post("/preferences/refresh", response_model=EffectivePreferenceSnapshotResponse)
    async def refresh_preferences(
        payload: ResolvePreferencesRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> EffectivePreferenceSnapshotResponse:
        return await service.resolve_preferences(identity, payload)

    return router
