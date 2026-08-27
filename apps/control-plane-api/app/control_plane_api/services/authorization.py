from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.resolution import PreferenceCatalog, ResolutionPolicyRegistry


class AgentCapability(StrEnum):
    RESOLVE_CONTEXT = "resolve_context"
    SUBMIT_CANDIDATES = "submit_candidates"
    INSPECT_PROVENANCE = "inspect_provenance"
    ADMINISTER_MEMORY = "administer_memory"


@dataclass(frozen=True, slots=True)
class AgentRegistration:
    agent_id: str
    consumer_domain: str
    capabilities: frozenset[AgentCapability]
    schema_grants: dict[str, AccessPermission]


class AuthorizationService:
    """Default-deny operation, domain, attribute, and schema authorization."""

    def __init__(
        self,
        registrations: tuple[AgentRegistration, ...],
        catalog: PreferenceCatalog,
        policies: ResolutionPolicyRegistry,
    ) -> None:
        self._registrations = {item.agent_id: item for item in registrations}
        self.catalog = catalog
        self.policies = policies

    def require_capability(
        self, agent_id: str, consumer_domain: str, capability: AgentCapability
    ) -> AgentRegistration:
        registration = self._registrations.get(agent_id)
        if registration is None:
            raise PermissionError(f"agent {agent_id!r} is not registered")
        if registration.consumer_domain != consumer_domain:
            raise PermissionError("registered agent domain does not match consumer domain")
        if capability not in registration.capabilities:
            raise PermissionError(f"agent {agent_id!r} lacks capability {capability.value}")
        return registration

    def require_schema_access(
        self,
        registration: AgentRegistration,
        schema_id: str,
        required: AccessPermission,
    ) -> None:
        granted = registration.schema_grants.get(schema_id, AccessPermission.NONE)
        allowed = {
            AccessPermission.READ: {AccessPermission.READ, AccessPermission.READ_WRITE},
            AccessPermission.WRITE: {AccessPermission.WRITE, AccessPermission.READ_WRITE},
            AccessPermission.READ_WRITE: {AccessPermission.READ_WRITE},
        }.get(required, set())
        if granted not in allowed:
            raise PermissionError(
                f"agent {registration.agent_id!r} lacks {required.value} access to schema {schema_id!r}"
            )

    def readable_domains(self, consumer_domain: str) -> tuple[str, ...]:
        return self.policies.domain_policy(consumer_domain).readable_domains

    def require_attribute_access(
        self, consumer_domain: str, attribute: str, *, write: bool
    ) -> None:
        definition = self.catalog.get(attribute)
        if definition is None:
            raise PermissionError(f"attribute {attribute!r} is not registered")
        domain_policy = self.policies.domain_policy(consumer_domain)
        allowed_domains = (
            domain_policy.writable_domains if write else domain_policy.readable_domains
        )
        allowed_consumers = definition.allowed_writers if write else definition.allowed_readers
        if (
            definition.owner_domain not in allowed_domains
            or consumer_domain not in allowed_consumers
        ):
            operation = "write" if write else "read"
            raise PermissionError(f"{operation} is not allowed for attribute {attribute!r}")
