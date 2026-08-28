from __future__ import annotations

import os
from dataclasses import dataclass

from control_plane_api.security.admin import AdminAuthenticator, AdminRole
from control_plane_api.security.authentication import (
    AgentAuthenticator,
    EntraAccessTokenAuthenticator,
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
class ControlPlaneApiSettings:
    database_url: str
    auth_enabled: bool
    google_id_token_audience: str | None
    admin_role_bindings_json: str = "{}"
    memory_backend: str = "mock"
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    memory_bank_resource_id: str | None = None
    admin_auth_mode: str = "bearer"
    iap_jwt_audience: str | None = None
    entra_auth_enabled: bool = False
    entra_tenant_id: str | None = None
    entra_api_audience: str | None = None
    entra_required_scope: str = "access_as_user"
    entra_platform_admin_role: str = "Platform.Admin"
    entra_platform_user_role: str = "Platform.User"

    @classmethod
    def from_environment(cls) -> ControlPlaneApiSettings:
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", "sqlite+aiosqlite:///./shared-memory-control-plane.db"
            ),
            auth_enabled=environment_bool("AUTH_ENABLED", False),
            google_id_token_audience=os.getenv("GOOGLE_ID_TOKEN_AUDIENCE"),
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
            entra_auth_enabled=environment_bool("ENTRA_AUTH_ENABLED", False),
            entra_tenant_id=os.getenv("ENTRA_TENANT_ID"),
            entra_api_audience=os.getenv("ENTRA_API_AUDIENCE"),
            entra_required_scope=os.getenv("ENTRA_REQUIRED_SCOPE", "access_as_user"),
            entra_platform_admin_role=os.getenv("ENTRA_PLATFORM_ADMIN_ROLE", "Platform.Admin"),
            entra_platform_user_role=os.getenv("ENTRA_PLATFORM_USER_ROLE", "Platform.User"),
        )

    def memory_store(self):
        from control_plane_api.integrations import MockMemoryStore, VertexMemoryBankStore

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
        token_role_mapping: dict[str, AdminRole] | None = None
        admin_auth_enabled = self.auth_enabled
        if self.entra_auth_enabled:
            admin_auth_enabled = True
            identity_authenticator = EntraAccessTokenAuthenticator(
                tenant_id=self.entra_tenant_id or "",
                audience=self.entra_api_audience or "",
                required_scope=self.entra_required_scope,
            )
            token_role_mapping = {
                self.entra_platform_admin_role: AdminRole.PLATFORM_ADMIN,
                self.entra_platform_user_role: AdminRole.PLATFORM_USER,
            }
        elif self.auth_enabled and self.admin_auth_mode == "iap":
            identity_authenticator = IapJwtAuthenticator(self.iap_jwt_audience or "")
        elif self.admin_auth_mode == "bearer":
            identity_authenticator = self.authenticator()
        else:
            raise ValueError("ADMIN_AUTH_MODE must be 'bearer' or 'iap'")
        return AdminAuthenticator(
            auth_enabled=admin_auth_enabled,
            google_authenticator=identity_authenticator,
            role_bindings_json=self.admin_role_bindings_json,
            token_role_mapping=token_role_mapping,
        )
