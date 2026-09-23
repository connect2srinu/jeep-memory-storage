from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from control_plane_api.api.admin.routes import create_admin_router
from control_plane_api.api.runtime.models import ApiError
from control_plane_api.api.runtime.routes import create_runtime_router
from control_plane_api.config.settings import ControlPlaneApiSettings
from control_plane_api.observability.runtime import (
    CorrelationAndMetricsMiddleware,
    RuntimeMetrics,
    correlation_id_context,
)
from control_plane_api.persistence.database import Database
from control_plane_api.persistence.runtime_repository import SqlAlchemyRuntimeControlPlaneRepository
from control_plane_api.repositories import MemoryStore
from control_plane_api.security.authentication import AuthenticationError
from control_plane_api.services.admin_service import (
    AdminControlPlaneService,
    ResourceConflictError,
    ResourceNotFoundError,
)
from control_plane_api.services.guided_setup import GuidedMemorySetupService
from control_plane_api.services.retention_service import RetentionService
from control_plane_api.services.runtime_service import RuntimeMemoryService
from control_plane_api.services.scope_registry import ScopeRegistry
from control_plane_api.services.vertex_provisioning import VertexContextProvisioner

API_DESCRIPTION = """
The **Control Plane API** is the single backend for the GEAP Control Panel. It exposes two planes:

* **Admin plane** (`/api/v1/admin`) — used by the Admin Console to govern organizations, projects,
  domains, scopes, schemas, the preference catalog, agents, grants, resolution and dynamic-memory
  policies, approvals, settings, health, and audit. PostgreSQL is the system of record.
* **Runtime plane** (`/api/v1/runtime`) — used by ADK agents to resolve their effective preference
  snapshot and submit governed writes. Schema selection, authorization, and conflict resolution are
  deterministic server operations; agents never call Memory Bank directly.

### Response envelope

Admin reads return `{ "data": {...} }` for a single record or `{ "items": [...] }` for a list.
Errors return `{ "code": ..., "message": ..., "correlationId": ... }` with the codes below. Every
response carries an `X-Correlation-Id` header that also appears in structured logs and audit events.

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_ARGUMENT` | Validation or cross-reference failure |
| 401 | `UNAUTHENTICATED` | Missing or invalid identity |
| 403 | `PERMISSION_DENIED` | Role, domain, or grant denial |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Existing active resource is incompatible |

### Authentication

Local development (`AUTH_ENABLED=false`) trusts the `X-Admin-User` / `X-Admin-Roles` /
`X-Admin-Domains` headers for the admin plane and `X-Agent-ID` for the runtime plane. Deployed
environments verify a Microsoft Entra ID or Google-signed token (or an IAP JWT assertion) and derive
roles from persisted organization/project membership.

Interactive docs: **Swagger UI** at `/docs`, **ReDoc** at `/redoc`, raw schema at `/openapi.json`.
"""

OPENAPI_TAGS = [
    {
        "name": "admin",
        "description": (
            "Control Panel plane. Governs the organization to project to domain hierarchy and every "
            "memory resource, with role- and membership-based authorization and immutable audit."
        ),
    },
    {
        "name": "runtime",
        "description": (
            "Agent-facing plane. Authenticated agents resolve their authorized preference snapshot "
            "and submit explicit or event-based writes; the platform selects the schema and resolves "
            "conflicts deterministically."
        ),
    },
]


def create_app(
    settings: ControlPlaneApiSettings | None = None,
    *,
    database: Database | None = None,
    store: MemoryStore | None = None,
) -> FastAPI:
    configured = settings or ControlPlaneApiSettings.from_environment()
    runtime_database = database or Database(configured.database_url)
    runtime_store = store or configured.memory_store()
    vertex_provisioner = (
        VertexContextProvisioner(
            project=configured.google_cloud_project or "",
            location=configured.google_cloud_location,
            resource_id=configured.memory_bank_resource_id or "",
            generation_model=configured.memory_bank_generation_model,
        )
        if configured.memory_backend == "vertex"
        else None
    )
    metrics = RuntimeMetrics()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await runtime_database.dispose()

    api = FastAPI(
        title="Control Plane API",
        version="1.0.0",
        summary="Governance and runtime API for the GEAP Control Panel.",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        contact={"name": "GEAP Platform Engineering"},
        license_info={"name": "Proprietary"},
        lifespan=lifespan,
    )
    api.state.database = runtime_database
    api.state.memory_store = runtime_store
    api.state.metrics = metrics
    api.add_middleware(CorrelationAndMetricsMiddleware, metrics=metrics)

    async def runtime_service() -> AsyncIterator[RuntimeMemoryService]:
        async with runtime_database.session() as session:
            yield RuntimeMemoryService(
                SqlAlchemyRuntimeControlPlaneRepository(session),
                runtime_store,
                ScopeRegistry(),
            )

    async def admin_service() -> AsyncIterator[AdminControlPlaneService]:
        async with runtime_database.session() as session:
            yield AdminControlPlaneService(session)

    async def guided_setup_service() -> AsyncIterator[GuidedMemorySetupService]:
        async with runtime_database.session() as session:
            yield GuidedMemorySetupService(session, runtime_store, vertex_provisioner)

    async def retention_service() -> AsyncIterator[RetentionService]:
        async with runtime_database.session() as session:
            yield RetentionService(session, runtime_store)

    api.include_router(
        create_runtime_router(
            authenticator=configured.authenticator(),
            service_dependency=runtime_service,
        )
    )
    api.include_router(
        create_admin_router(
            authenticator=configured.admin_authenticator(),
            service_dependency=admin_service,
            guided_service_dependency=guided_setup_service,
            retention_service_dependency=retention_service,
        )
    )

    @api.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, exc: AuthenticationError) -> JSONResponse:
        payload = ApiError(
            code="UNAUTHENTICATED",
            message=str(exc),
            correlationId=correlation_id_context.get(),
        )
        return JSONResponse(status_code=401, content=payload.model_dump(by_alias=True))

    @api.exception_handler(PermissionError)
    async def authorization_error(_: Request, exc: PermissionError) -> JSONResponse:
        payload = ApiError(
            code="PERMISSION_DENIED",
            message=str(exc),
            correlationId=correlation_id_context.get(),
        )
        return JSONResponse(status_code=403, content=payload.model_dump(by_alias=True))

    async def invalid_request(_: Request, exc: Exception) -> JSONResponse:
        payload = ApiError(
            code="INVALID_ARGUMENT",
            message=str(exc),
            correlationId=correlation_id_context.get(),
        )
        return JSONResponse(status_code=400, content=payload.model_dump(by_alias=True))

    api.add_exception_handler(KeyError, invalid_request)
    api.add_exception_handler(ValueError, invalid_request)

    @api.exception_handler(ResourceNotFoundError)
    async def resource_not_found(_: Request, exc: ResourceNotFoundError) -> JSONResponse:
        payload = ApiError(
            code="NOT_FOUND",
            message=str(exc),
            correlationId=correlation_id_context.get(),
        )
        return JSONResponse(status_code=404, content=payload.model_dump(by_alias=True))

    @api.exception_handler(ResourceConflictError)
    async def resource_conflict(_: Request, exc: ResourceConflictError) -> JSONResponse:
        payload = ApiError(
            code="CONFLICT",
            message=str(exc),
            correlationId=correlation_id_context.get(),
        )
        return JSONResponse(status_code=409, content=payload.model_dump(by_alias=True))

    @api.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "application": "control-plane-api"}

    @api.get("/internal/metrics", include_in_schema=False)
    async def metric_snapshot() -> dict[str, int]:
        return metrics.snapshot()

    return api
