from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from control_plane_api.domain.preferences import PreferenceSource


class ResolutionStrategy(StrEnum):
    SOURCE_PRIORITY = "SOURCE_PRIORITY"
    DOMAIN_PRIORITY = "DOMAIN_PRIORITY"
    EXPLICIT_OVER_INFERRED = "EXPLICIT_OVER_INFERRED"
    MOST_RECENT = "MOST_RECENT"
    HIGHEST_CONFIDENCE = "HIGHEST_CONFIDENCE"


@dataclass(frozen=True, slots=True)
class PreferenceDefinition:
    key: str
    owner_domain: str
    resolution_key: str
    allowed_readers: tuple[str, ...]
    allowed_writers: tuple[str, ...]


class PreferenceCatalog:
    def __init__(self, definitions: tuple[PreferenceDefinition, ...]) -> None:
        self._definitions = {item.key: item for item in definitions}

    def get(self, key: str) -> PreferenceDefinition | None:
        return self._definitions.get(key)

    def logical_key(self, key: str) -> str:
        definition = self.get(key)
        return definition.resolution_key if definition else key.rsplit(".", 1)[-1]


@dataclass(frozen=True, slots=True)
class DomainAccessPolicy:
    domain: str
    readable_domains: tuple[str, ...]
    writable_domains: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    id: str
    source_priority: tuple[PreferenceSource, ...]
    domain_priority: tuple[str, ...]
    strategies: tuple[ResolutionStrategy, ...]
    minimum_confidence: float = 0.0


class ResolutionPolicyRegistry:
    def __init__(
        self,
        *,
        domain_policies: tuple[DomainAccessPolicy, ...],
        policies: dict[str, ResolutionPolicy],
        default_policy: ResolutionPolicy,
        version: str,
    ) -> None:
        self._domains = {item.domain: item for item in domain_policies}
        self._policies = policies
        self.default_policy = default_policy
        self.version = version

    def domain_policy(self, domain: str) -> DomainAccessPolicy:
        return self._domains.get(domain, DomainAccessPolicy(domain, (domain,), (domain,)))

    def resolution_policy(self, logical_key: str) -> ResolutionPolicy:
        return self._policies.get(logical_key, self.default_policy)
