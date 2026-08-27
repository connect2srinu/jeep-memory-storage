from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Request

from .authentication import AgentAuthenticator, AuthenticationError


class AdminRole(StrEnum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    DOMAIN_ADMIN = "DOMAIN_ADMIN"
    SCHEMA_OWNER = "SCHEMA_OWNER"
    AGENT_OWNER = "AGENT_OWNER"
    VIEWER = "VIEWER"


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    subject: str
    principal: str
    roles: frozenset[AdminRole]
    domain_ids: frozenset[str]

    def has_any_role(self, *roles: AdminRole) -> bool:
        return bool(self.roles.intersection(roles))


class AdminAuthenticator:
    """Authenticate admin users and bind trusted roles/domain ownership."""

    def __init__(
        self,
        *,
        auth_enabled: bool,
        google_authenticator: AgentAuthenticator,
        role_bindings_json: str = "{}",
    ) -> None:
        self.auth_enabled = auth_enabled
        self.google_authenticator = google_authenticator
        try:
            bindings = json.loads(role_bindings_json or "{}")
        except json.JSONDecodeError as error:
            raise ValueError("ADMIN_ROLE_BINDINGS_JSON must be valid JSON") from error
        if not isinstance(bindings, dict):
            raise TypeError("ADMIN_ROLE_BINDINGS_JSON must be a JSON object")
        self.bindings = bindings

    @staticmethod
    def _roles(values: list[str]) -> frozenset[AdminRole]:
        try:
            return frozenset(AdminRole(value.strip()) for value in values if value.strip())
        except ValueError as error:
            raise AuthenticationError("admin role binding contains an unsupported role") from error

    async def authenticate(self, request: Request) -> AdminPrincipal:
        if not self.auth_enabled:
            principal = request.headers.get("x-admin-user", "").strip()
            roles = self._roles(request.headers.get("x-admin-roles", "").split(","))
            domains = frozenset(
                value.strip()
                for value in request.headers.get("x-admin-domains", "").split(",")
                if value.strip()
            )
            if not principal or not roles:
                raise AuthenticationError(
                    "X-Admin-User and X-Admin-Roles are required when AUTH_ENABLED=false"
                )
            return AdminPrincipal(
                subject=f"local:{principal}",
                principal=principal,
                roles=roles,
                domain_ids=domains,
            )

        identity = await self.google_authenticator.authenticate(request)
        binding = self.bindings.get(identity.principal)
        if not isinstance(binding, dict):
            raise AuthenticationError("verified admin principal has no role binding")
        roles = self._roles([str(value) for value in binding.get("roles", [])])
        if not roles:
            raise AuthenticationError("verified admin principal has no assigned roles")
        return AdminPrincipal(
            subject=identity.subject,
            principal=identity.principal,
            roles=roles,
            domain_ids=frozenset(str(value) for value in binding.get("domains", [])),
        )


class AdminAuthorizer:
    @staticmethod
    def require_read(principal: AdminPrincipal) -> None:
        if not principal.roles:
            raise PermissionError("admin principal has no readable role")

    @staticmethod
    def require_platform(principal: AdminPrincipal) -> None:
        if AdminRole.PLATFORM_ADMIN not in principal.roles:
            raise PermissionError("PLATFORM_ADMIN role is required")

    @staticmethod
    def require_domain(
        principal: AdminPrincipal,
        domain_id: str,
        *allowed_roles: AdminRole,
    ) -> None:
        if AdminRole.PLATFORM_ADMIN in principal.roles:
            return
        roles = allowed_roles or (
            AdminRole.DOMAIN_ADMIN,
            AdminRole.SCHEMA_OWNER,
            AdminRole.AGENT_OWNER,
        )
        if domain_id not in principal.domain_ids or not principal.has_any_role(*roles):
            raise PermissionError(f"admin principal does not own domain {domain_id}")
