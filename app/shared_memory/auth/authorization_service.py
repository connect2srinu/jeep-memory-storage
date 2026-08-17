from __future__ import annotations

from dataclasses import dataclass

from app.shared_memory.auth.consumer_registry import ConsumerCapability, ConsumerRegistry
from app.shared_memory.catalog import CatalogEntry
from app.shared_memory.policies import PreferencePolicyRegistry


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    action: str
    consumer_domain: str
    owner_domain: str
    reason: str


class AuthorizationService:
    """POC policy enforcement point; replace identity verification without changing callers."""

    def __init__(
        self,
        policies: PreferencePolicyRegistry,
        consumers: ConsumerRegistry | None = None,
    ) -> None:
        self.policies = policies
        self.consumers = consumers or ConsumerRegistry.default()

    def authenticate(self, user_id: str, agent_id: str) -> None:
        if not user_id.strip() or not agent_id.strip():
            raise PermissionError("authenticated user_id and agent_id are required")

    def authorize_consumer(
        self,
        agent_id: str,
        consumer_domain: str,
        capability: ConsumerCapability,
    ) -> None:
        self.consumers.require(agent_id, consumer_domain, capability)

    def readable_domains(self, consumer_domain: str) -> tuple[str, ...]:
        return self.policies.domain_policy(consumer_domain).read

    def can_read(
        self, consumer_domain: str, owner_domain: str, entry: CatalogEntry | None = None
    ) -> AuthorizationDecision:
        domain_allowed = owner_domain in self.readable_domains(consumer_domain)
        entry_allowed = entry is None or consumer_domain in entry.allowed_readers
        allowed = domain_allowed and entry_allowed
        return AuthorizationDecision(
            allowed,
            "read",
            consumer_domain,
            owner_domain,
            "allowed_by_domain_and_catalog" if allowed else "read_not_allowed",
        )

    def can_write(
        self, consumer_domain: str, owner_domain: str, entry: CatalogEntry | None = None
    ) -> AuthorizationDecision:
        policy = self.policies.domain_policy(consumer_domain)
        domain_allowed = owner_domain in policy.write
        entry_allowed = entry is None or consumer_domain in entry.allowed_writers
        allowed = domain_allowed and entry_allowed
        return AuthorizationDecision(
            allowed,
            "write",
            consumer_domain,
            owner_domain,
            "allowed_by_domain_and_catalog" if allowed else "write_not_allowed",
        )
