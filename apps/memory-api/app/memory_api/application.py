from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from memory_api.api.admin.routes import create_admin_router
from memory_api.api.runtime.models import ApiError
from memory_api.api.runtime.routes import create_runtime_router
from memory_api.config.settings import MemoryApiSettings
from memory_api.observability.runtime import (
    CorrelationAndMetricsMiddleware,
    RuntimeMetrics,
    correlation_id_context,
)
from memory_api.persistence.database import Database
from memory_api.persistence.runtime_repository import SqlAlchemyRuntimeControlPlaneRepository
from memory_api.repositories import MemoryStore
from memory_api.security.authentication import AuthenticationError
from memory_api.services.admin_service import (
    AdminControlPlaneService,
    ResourceConflictError,
    ResourceNotFoundError,
)
from memory_api.services.runtime_service import RuntimeMemoryService
from memory_api.services.scope_registry import ScopeRegistry


def create_app(
    settings: MemoryApiSettings | None = None,
    *,
    database: Database | None = None,
    store: MemoryStore | None = None,
) -> FastAPI:
    configured = settings or MemoryApiSettings.from_environment()
    runtime_database = database or Database(configured.database_url)
    runtime_store = store or configured.memory_store()
    metrics = RuntimeMetrics()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await runtime_database.dispose()

    api = FastAPI(
        title="Shared Memory Platform API",
        version="1.0.0",
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
        return {"status": "ok", "application": "memory-api"}

    @api.get("/internal/metrics", include_in_schema=False)
    async def metric_snapshot() -> dict[str, int]:
        return metrics.snapshot()

    if configured.include_legacy_routes:
        from app.api import api as legacy_api

        api.include_router(legacy_api.router)
    return api
