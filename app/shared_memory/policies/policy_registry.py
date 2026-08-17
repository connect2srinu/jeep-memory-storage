from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files

from app.shared_memory.models import PreferenceSource


class ResolutionStrategy(StrEnum):
    SOURCE_PRIORITY = "SOURCE_PRIORITY"
    DOMAIN_PRIORITY = "DOMAIN_PRIORITY"
    EXPLICIT_OVER_INFERRED = "EXPLICIT_OVER_INFERRED"
    MOST_RECENT = "MOST_RECENT"
    HIGHEST_CONFIDENCE = "HIGHEST_CONFIDENCE"


@dataclass(frozen=True, slots=True)
class DomainAccessPolicy:
    domain: str
    read: tuple[str, ...]
    write: tuple[str, ...]
    isolation: str = "standard"


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    policy_id: str
    source_priority: tuple[PreferenceSource, ...]
    domain_priority: tuple[str, ...]
    strategies: tuple[ResolutionStrategy, ...]
    minimum_confidence: float = 0.0


class PreferencePolicyRegistry:
    def __init__(
        self,
        domain_policies: dict[str, DomainAccessPolicy],
        resolution_policies: dict[str, ResolutionPolicy],
        default_policy: ResolutionPolicy,
        version: str,
    ) -> None:
        self.domain_policies = domain_policies
        self.resolution_policies = resolution_policies
        self.default_policy = default_policy
        self.version = version

    @classmethod
    def default(cls, minimum_confidence: float = 0.7) -> PreferencePolicyRegistry:
        package = files("app.shared_memory.policies")
        domain_payload = json.loads(
            package.joinpath("domain_policy.json").read_text(encoding="utf-8")
        )
        resolution_payload = json.loads(
            package.joinpath("resolution_policy.json").read_text(encoding="utf-8")
        )
        domains = {
            name: DomainAccessPolicy(
                domain=name,
                read=tuple(item.get("read", [])),
                write=tuple(item.get("write", [])),
                isolation=item.get("isolation", "standard"),
            )
            for name, item in domain_payload["domains"].items()
        }
        default_data = resolution_payload["default"]

        def build(policy_id: str, item: dict[str, object]) -> ResolutionPolicy:
            return ResolutionPolicy(
                policy_id=policy_id,
                source_priority=tuple(
                    PreferenceSource(value)
                    for value in item.get("source_priority", default_data["source_priority"])
                ),
                domain_priority=tuple(item.get("domain_priority", [])),
                strategies=tuple(
                    ResolutionStrategy(value)
                    for value in item.get("strategies", default_data["strategies"])
                ),
                minimum_confidence=float(item.get("minimum_confidence", minimum_confidence)),
            )

        default_policy = build("default", default_data)
        policies = {
            key: build(key, value) for key, value in resolution_payload["policies"].items()
        }
        version = f"{domain_payload.get('version', '1')}:{resolution_payload.get('version', '1')}"
        return cls(domains, policies, default_policy, version)

    def domain_policy(self, consumer_domain: str) -> DomainAccessPolicy:
        return self.domain_policies.get(
            consumer_domain,
            DomainAccessPolicy(consumer_domain, (consumer_domain,), (consumer_domain,), "strict"),
        )

    def resolution_policy(self, logical_key: str) -> ResolutionPolicy:
        return self.resolution_policies.get(logical_key, self.default_policy)

