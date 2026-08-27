from __future__ import annotations

# FastAPI dependencies are intentionally declared as parameter defaults.
# ruff: noqa: B008
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Depends, Query, Request

from control_plane_api.api.admin.models import (
    AccessDecision,
    AccessRequestCreate,
    AdminRecord,
    AdminRecordList,
    AgentCreate,
    DomainCreate,
    DynamicMemoryPolicyCreate,
    GuidedMemorySetupActivation,
    GuidedMemorySetupPreview,
    GuidedMemorySetupRequest,
    MembershipCreate,
    OrganizationCreate,
    PreferenceCreate,
    ProjectCreate,
    ResolutionPolicyCreate,
    ResourceUpdate,
    SchemaCreate,
    SchemaVersionChange,
    ScopeCreate,
)
from control_plane_api.domain import AccessRequestStatus
from control_plane_api.security.admin import AdminAuthenticator, AdminPrincipal
from control_plane_api.services.admin_service import AdminControlPlaneService
from control_plane_api.services.guided_setup import GuidedMemorySetupService

ServiceDependency = Callable[[], AsyncIterator[AdminControlPlaneService]]
GuidedServiceDependency = Callable[[], AsyncIterator[GuidedMemorySetupService]]


def create_admin_router(
    *,
    authenticator: AdminAuthenticator,
    service_dependency: ServiceDependency,
    guided_service_dependency: GuidedServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

    async def principal(request: Request) -> AdminPrincipal:
        return await authenticator.authenticate(request)

    @router.post("/memory-setups/preview", response_model=GuidedMemorySetupPreview)
    async def preview_memory_setup(
        payload: GuidedMemorySetupRequest,
        identity: AdminPrincipal = Depends(principal),
        service: GuidedMemorySetupService = Depends(guided_service_dependency),
    ) -> GuidedMemorySetupPreview:
        return await service.preview(identity, payload)

    @router.post(
        "/memory-setups/activate",
        response_model=GuidedMemorySetupActivation,
        status_code=201,
    )
    async def activate_memory_setup(
        payload: GuidedMemorySetupRequest,
        identity: AdminPrincipal = Depends(principal),
        service: GuidedMemorySetupService = Depends(guided_service_dependency),
    ) -> GuidedMemorySetupActivation:
        return await service.activate(identity, payload)

    async def listed(
        resource: str,
        identity: AdminPrincipal,
        service: AdminControlPlaneService,
        organization_id: str | None = None,
    ) -> AdminRecordList:
        return AdminRecordList(
            items=await service.list_resources(identity, resource, organization_id)
        )

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

    @router.get("/organization-hierarchy", response_model=AdminRecord)
    async def get_organization_hierarchy(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.organization_hierarchy(identity))

    @router.post(
        "/organizations/{organization_id}/members",
        response_model=AdminRecord,
        status_code=201,
    )
    async def add_organization_member(
        organization_id: str,
        payload: MembershipCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.add_organization_member(identity, organization_id, payload)
        )

    @router.post(
        "/projects/{project_id}/members",
        response_model=AdminRecord,
        status_code=201,
    )
    async def add_project_member(
        project_id: str,
        payload: MembershipCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.add_project_member(identity, project_id, payload))

    @router.get("/organizations", response_model=AdminRecordList)
    async def list_organizations(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("organizations", identity, service)

    @router.post("/organizations", response_model=AdminRecord, status_code=201)
    async def create_organization(
        payload: OrganizationCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_resource(identity, "organizations", payload))

    @router.get("/organizations/{resource_id}", response_model=AdminRecord)
    async def get_organization(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("organizations", resource_id, identity, service)

    @router.patch("/organizations/{resource_id}", response_model=AdminRecord)
    async def update_organization(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("organizations", resource_id, payload, identity, service)

    @router.get("/projects", response_model=AdminRecordList)
    async def list_projects(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("projects", identity, service)

    @router.post("/projects", response_model=AdminRecord, status_code=201)
    async def create_project(
        payload: ProjectCreate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(data=await service.create_resource(identity, "projects", payload))

    @router.get("/projects/{resource_id}", response_model=AdminRecord)
    async def get_project(
        resource_id: str,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await fetched("projects", resource_id, identity, service)

    @router.patch("/projects/{resource_id}", response_model=AdminRecord)
    async def update_project(
        resource_id: str,
        payload: ResourceUpdate,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await updated("projects", resource_id, payload, identity, service)

    @router.get("/domains", response_model=AdminRecordList)
    async def list_domains(
        organization_id: str | None = Query(default=None, alias="organizationId"),
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("domains", identity, service, organization_id)

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
        return AdminRecord(data=await service.submit_domain_change(identity, resource_id, payload))

    @router.get("/scopes", response_model=AdminRecordList)
    async def list_scopes(
        organization_id: str | None = Query(default=None, alias="organizationId"),
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("scopes", identity, service, organization_id)

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
        organization_id: str | None = Query(default=None, alias="organizationId"),
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("schemas", identity, service, organization_id)

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

    @router.post(
        "/schemas/{resource_id}/versions",
        response_model=AdminRecord,
        status_code=202,
    )
    async def create_schema_version_change(
        resource_id: str,
        payload: SchemaVersionChange,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.submit_schema_version_change(identity, resource_id, payload)
        )

    @router.get("/preference-catalog", response_model=AdminRecordList)
    async def list_preferences(
        organization_id: str | None = Query(default=None, alias="organizationId"),
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("preference-catalog", identity, service, organization_id)

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
        organization_id: str | None = Query(default=None, alias="organizationId"),
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return await listed("agents", identity, service, organization_id)

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

    @router.get("/resource-change-requests", response_model=AdminRecordList)
    async def list_resource_change_requests(
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecordList:
        return AdminRecordList(items=await service.list_resource_change_requests(identity))

    async def change_decision(
        request_id: str,
        decision: str,
        payload: AccessDecision,
        identity: AdminPrincipal,
        service: AdminControlPlaneService,
    ) -> AdminRecord:
        return AdminRecord(
            data=await service.decide_resource_change(
                identity, request_id, decision, reason=payload.reason
            )
        )

    @router.post("/resource-change-requests/{request_id}/approve", response_model=AdminRecord)
    async def approve_resource_change(
        request_id: str,
        payload: AccessDecision,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await change_decision(request_id, "APPROVED", payload, identity, service)

    @router.post("/resource-change-requests/{request_id}/reject", response_model=AdminRecord)
    async def reject_resource_change(
        request_id: str,
        payload: AccessDecision,
        identity: AdminPrincipal = Depends(principal),
        service: AdminControlPlaneService = Depends(service_dependency),
    ) -> AdminRecord:
        return await change_decision(request_id, "REJECTED", payload, identity, service)

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
