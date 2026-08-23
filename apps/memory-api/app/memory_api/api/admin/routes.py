from __future__ import annotations

# FastAPI dependencies are intentionally declared as parameter defaults.
# ruff: noqa: B008
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Depends, Request

from memory_api.api.admin.models import (
    AccessDecision,
    AccessRequestCreate,
    AdminRecord,
    AdminRecordList,
    AgentCreate,
    DomainCreate,
    DynamicMemoryPolicyCreate,
    PreferenceCreate,
    ResolutionPolicyCreate,
    ResourceUpdate,
    SchemaCreate,
    ScopeCreate,
)
from memory_api.domain import AccessRequestStatus
from memory_api.security.admin import AdminAuthenticator, AdminPrincipal
from memory_api.services.admin_service import AdminControlPlaneService

ServiceDependency = Callable[[], AsyncIterator[AdminControlPlaneService]]


def create_admin_router(
    *,
    authenticator: AdminAuthenticator,
    service_dependency: ServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

    async def principal(request: Request) -> AdminPrincipal:
        return await authenticator.authenticate(request)

    async def listed(
        resource: str, identity: AdminPrincipal, service: AdminControlPlaneService
    ) -> AdminRecordList:
        return AdminRecordList(items=await service.list_resources(identity, resource))

    async def fetched(
        resource: str,
        resource_id: str,
        identity: AdminPrincipal,
        service: AdminControlPlaneService,
    ) -> AdminRecord:
        return AdminRecord(data=await service.get_resource(identity, resource, resource_id))

    async def updated(
        resource: str,
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal,
        service: AdminControlPlaneService,
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.update_resource(identity, resource, resource_id, payload)
        )

    @router.get("/domains", response_model=AdminRecordList)
    async def list_domains(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("domains", identity, service)

    @router.post("/domains", response_model=AdminRecord, status_code=201)
    async def create_domain(
        payload: DomainCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_resource(identity, "domains", payload))

    @router.get("/domains/{resource_id}", response_model=AdminRecord)
    async def get_domain(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("domains", resource_id, identity, service)

    @router.patch("/domains/{resource_id}", response_model=AdminRecord)
    async def update_domain(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("domains", resource_id, payload, identity, service)

    @router.get("/scopes", response_model=AdminRecordList)
    async def list_scopes(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("scopes", identity, service)

    @router.post("/scopes", response_model=AdminRecord, status_code=201)
    async def create_scope(
        payload: ScopeCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_resource(identity, "scopes", payload))

    @router.get("/scopes/{resource_id}", response_model=AdminRecord)
    async def get_scope(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("scopes", resource_id, identity, service)

    @router.patch("/scopes/{resource_id}", response_model=AdminRecord)
    async def update_scope(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("scopes", resource_id, payload, identity, service)

    @router.get("/schemas", response_model=AdminRecordList)
    async def list_schemas(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("schemas", identity, service)

    @router.post("/schemas", response_model=AdminRecord, status_code=201)
    async def create_schema(
        payload: SchemaCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_resource(identity, "schemas", payload))

    @router.get("/schemas/{resource_id}", response_model=AdminRecord)
    async def get_schema(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("schemas", resource_id, identity, service)

    @router.patch("/schemas/{resource_id}", response_model=AdminRecord)
    async def update_schema(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("schemas", resource_id, payload, identity, service)

    @router.get("/preference-catalog", response_model=AdminRecordList)
    async def list_preferences(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("preference-catalog", identity, service)

    @router.post("/preference-catalog", response_model=AdminRecord, status_code=201)
    async def create_preference(
        payload: PreferenceCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.create_resource(identity, "preference-catalog", payload)
        )

    @router.get("/preference-catalog/{resource_id}", response_model=AdminRecord)
    async def get_preference(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("preference-catalog", resource_id, identity, service)

    @router.patch("/preference-catalog/{resource_id}", response_model=AdminRecord)
    async def update_preference(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("preference-catalog", resource_id, payload, identity, service)

    @router.get("/agents", response_model=AdminRecordList)
    async def list_agents(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("agents", identity, service)

    @router.post("/agents", response_model=AdminRecord, status_code=201)
    async def create_agent(
        payload: AgentCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_resource(identity, "agents", payload))

    @router.get("/agents/{resource_id}", response_model=AdminRecord)
    async def get_agent(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("agents", resource_id, identity, service)

    @router.patch("/agents/{resource_id}", response_model=AdminRecord)
    async def update_agent(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("agents", resource_id, payload, identity, service)

    @router.get("/resolution-policies", response_model=AdminRecordList)
    async def list_resolution_policies(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("resolution-policies", identity, service)

    @router.post("/resolution-policies", response_model=AdminRecord, status_code=201)
    async def create_resolution_policy(
        payload: ResolutionPolicyCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.create_resource(identity, "resolution-policies", payload)
        )

    @router.get("/resolution-policies/{resource_id}", response_model=AdminRecord)
    async def get_resolution_policy(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("resolution-policies", resource_id, identity, service)

    @router.patch("/resolution-policies/{resource_id}", response_model=AdminRecord)
    async def update_resolution_policy(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("resolution-policies", resource_id, payload, identity, service)

    @router.get("/dynamic-memory-policies", response_model=AdminRecordList)
    async def list_dynamic_policies(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("dynamic-memory-policies", identity, service)

    @router.post("/dynamic-memory-policies", response_model=AdminRecord, status_code=201)
    async def create_dynamic_policy(
        payload: DynamicMemoryPolicyCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.create_resource(identity, "dynamic-memory-policies", payload)
        )

    @router.get("/dynamic-memory-policies/{resource_id}", response_model=AdminRecord)
    async def get_dynamic_policy(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("dynamic-memory-policies", resource_id, identity, service)

    @router.patch("/dynamic-memory-policies/{resource_id}", response_model=AdminRecord)
    async def update_dynamic_policy(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("dynamic-memory-policies", resource_id, payload, identity, service)

    @router.get("/access-requests", response_model=AdminRecordList)
    async def list_access_requests(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return AdminRecordList(items=await service.list_access_requests(identity))

    @router.post("/access-requests", response_model=AdminRecord, status_code=201)
    async def create_access_request(
        payload: AccessRequestCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_access_request(identity, payload))

    async def decision(
        request_id: str,
        status: AccessRequestStatus,
        payload: AccessDecision,
        identity: AdminPrincipal,
        service: AdminControlPlaneService,
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.decide_access_request(
                identity,
                request_id,
                status,
                expiration=payload.expiration,
                reason=payload.reason,
            )
        )

    @router.post("/access-requests/{request_id}/approve", response_model=AdminRecord)
    async def approve_access_request(
        request_id: str,
        payload: AccessDecision,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await decision(request_id, AccessRequestStatus.APPROVED, payload, identity, service)

    @router.post("/access-requests/{request_id}/reject", response_model=AdminRecord)
    async def reject_access_request(
        request_id: str,
        payload: AccessDecision,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await decision(request_id, AccessRequestStatus.REJECTED, payload, identity, service)

    @router.post("/access-requests/{request_id}/revoke", response_model=AdminRecord)
    async def revoke_access_request(
        request_id: str,
        payload: AccessDecision,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await decision(request_id, AccessRequestStatus.REVOKED, payload, identity, service)

    @router.post("/access-requests/{request_id}/expire", response_model=AdminRecord)
    async def expire_access_request(
        request_id: str,
        payload: AccessDecision,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await decision(request_id, AccessRequestStatus.EXPIRED, payload, identity, service)

    @router.get("/audit", response_model=AdminRecordList)
    async def list_audit(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return AdminRecordList(items=await service.list_audit(identity))

    return router
