from __future__ import annotations

import os
from dataclasses import dataclass

from memory_api.security.admin import AdminAuthenticator
from memory_api.security.authentication import (
    AgentAuthenticator,
    GoogleIdTokenAuthenticator,
    IapJwtAuthenticator,
    LocalAgentAuthenticator,
)


def environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class MemoryApiSettings:
    database_url: str
    auth_enabled: bool
    google_id_token_audience: str | None
    include_legacy_routes: bool = False
    admin_role_bindings_json: str = "{}"
    memory_backend: str = "mock"
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    memory_bank_resource_id: str | None = None
    admin_auth_mode: str = "bearer"
    iap_jwt_audience: str | None = None

    @classmethod
    def from_environment(cls) -> MemoryApiSettings:
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", "sqlite+aiosqlite:///./shared-memory-control-plane.db"
            ),
            auth_enabled=environment_bool("AUTH_ENABLED", False),
            google_id_token_audience=os.getenv("GOOGLE_ID_TOKEN_AUDIENCE"),
            include_legacy_routes=environment_bool("INCLUDE_LEGACY_ROUTES", False),
            admin_role_bindings_json=os.getenv("ADMIN_ROLE_BINDINGS_JSON", "{}"),
            memory_backend=os.getenv("MEMORY_BACKEND", "mock").strip().lower(),
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            memory_bank_resource_id=(
                os.getenv("AGENT_PLATFORM_MEMORY_BANK_ID")
                or os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
            ),
            admin_auth_mode=os.getenv("ADMIN_AUTH_MODE", "bearer").strip().lower(),
            iap_jwt_audience=os.getenv("IAP_JWT_AUDIENCE"),
        )

    def memory_store(self):
        from memory_api.integrations import MockMemoryStore, VertexMemoryBankStore

        if self.memory_backend == "mock":
            return MockMemoryStore()
        if self.memory_backend == "vertex":
            return VertexMemoryBankStore.from_config(
                project=self.google_cloud_project or "",
                location=self.google_cloud_location,
                resource_id=self.memory_bank_resource_id or "",
            )
        raise ValueError("MEMORY_BACKEND must be 'mock' or 'vertex'")

    def authenticator(self) -> AgentAuthenticator:
        if not self.auth_enabled:
            return LocalAgentAuthenticator()
        return GoogleIdTokenAuthenticator(self.google_id_token_audience or "")

    def admin_authenticator(self) -> AdminAuthenticator:
        if self.auth_enabled and self.admin_auth_mode == "iap":
            identity_authenticator = IapJwtAuthenticator(self.iap_jwt_audience or "")
        elif self.admin_auth_mode == "bearer":
            identity_authenticator = self.authenticator()
        else:
            raise ValueError("ADMIN_AUTH_MODE must be 'bearer' or 'iap'")
        return AdminAuthenticator(
            auth_enabled=self.auth_enabled,
            google_authenticator=identity_authenticator,
            role_bindings_json=self.admin_role_bindings_json,
        )
