from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Depends, Request

from control_plane_api.api.runtime.models import (
    DynamicMemoryWrite,
    EffectivePreferenceSnapshotResponse,
    ExplicitPreferenceUpdate,
    ForgetMemoryRequest,
    HouseholdMemberAddRequest,
    HouseholdMemberMergeRequest,
    HouseholdMemberUpdateRequest,
    HouseholdMemberWriteRequest,
    MemoryEventRequest,
    PreferenceForgetRequest,
    PreferenceMoveRequest,
    PurgeMemoryRequest,
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

    @router.post("/memory/forget")
    async def forget_memory(
        payload: ForgetMemoryRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> dict[str, object]:
        return await service.forget_user_memories(identity, payload)

    @router.post("/memory/purge")
    async def purge_memory(
        payload: PurgeMemoryRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> dict[str, object]:
        return await service.purge_memories(identity, payload)

    @router.put("/preferences/{attribute}", response_model=RuntimeMutationResponse)
    async def update_preference(
        attribute: str,
        payload: ExplicitPreferenceUpdate,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.update_preference(identity, attribute, payload)

    @router.post("/preferences/{attribute}/forget", response_model=RuntimeMutationResponse)
    async def forget_preference(
        attribute: str,
        payload: PreferenceForgetRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.forget_preference(identity, attribute, payload)

    @router.post("/preferences/{attribute}/move", response_model=RuntimeMutationResponse)
    async def move_preference(
        attribute: str,
        payload: PreferenceMoveRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.move_preference(identity, attribute, payload)

    @router.post("/household/members", response_model=RuntimeMutationResponse)
    async def add_household_member(
        payload: HouseholdMemberAddRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.add_household_member(identity, payload)

    @router.post("/household/members/merge", response_model=RuntimeMutationResponse)
    async def merge_household_members(
        payload: HouseholdMemberMergeRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.merge_household_members(identity, payload)

    @router.patch("/household/members/{member_id}", response_model=RuntimeMutationResponse)
    async def update_household_member(
        member_id: str,
        payload: HouseholdMemberUpdateRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> RuntimeMutationResponse:
        return await service.update_household_member(identity, member_id, payload)

    @router.put("/households/{household_id}/members/{member_id}")
    async def upsert_household_member(
        household_id: str,
        member_id: str,
        payload: HouseholdMemberWriteRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> dict[str, object]:
        return await service.upsert_household_member(identity, household_id, member_id, payload)

    @router.delete("/households/{household_id}/members/{member_id}")
    async def deactivate_household_member(
        household_id: str,
        member_id: str,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> dict[str, object]:
        return await service.deactivate_household_member(identity, household_id, member_id)

    @router.post("/preferences/refresh", response_model=EffectivePreferenceSnapshotResponse)
    async def refresh_preferences(
        payload: ResolvePreferencesRequest,
        identity: AuthenticatedPrincipal = Depends(principal),  # noqa: B008
        service: RuntimeMemoryService = Depends(service_dependency),  # noqa: B008
    ) -> EffectivePreferenceSnapshotResponse:
        return await service.resolve_preferences(identity, payload)

    return router
