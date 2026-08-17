from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import (
    EffectivePreferenceContext,
    Preference,
    PreferenceSource,
    ResolvedPreference,
)
from app.shared_memory.policies import (
    PreferencePolicyRegistry,
    ResolutionPolicy,
    ResolutionStrategy,
)


class PreferenceResolver:
    """Pure deterministic resolver; it performs no I/O and has no model dependency."""

    def __init__(self, catalog: PreferenceCatalog, policies: PreferencePolicyRegistry) -> None:
        self.catalog = catalog
        self.policies = policies

    def resolve(
        self,
        *,
        user_id: str,
        session_id: str,
        consumer_domain: str,
        agent_id: str,
        preferences: list[Preference],
        readable_domains: tuple[str, ...],
        now: datetime | None = None,
        warnings: tuple[str, ...] = (),
    ) -> EffectivePreferenceContext:
        current = now or datetime.now(UTC)
        grouped: dict[str, list[Preference]] = defaultdict(list)
        for preference in preferences:
            if preference.owner_domain not in readable_domains or preference.is_expired(current):
                continue
            logical_key = self.catalog.logical_key(preference.key, preference.owner_domain)
            policy = self.policies.resolution_policy(logical_key)
            if (
                preference.source
                in {PreferenceSource.DYNAMIC_MEMORY, PreferenceSource.INFERRED_MEMORY}
                and preference.confidence is not None
                and preference.confidence < policy.minimum_confidence
            ):
                continue
            grouped[logical_key].append(preference)

        resolved: dict[str, ResolvedPreference] = {}
        for logical_key, candidates in grouped.items():
            policy = self.policies.resolution_policy(logical_key)
            selected = min(candidates, key=lambda item: self._rank(item, policy))
            resolved[logical_key] = ResolvedPreference(
                preference=selected,
                resolution_reason=self._reason(selected, candidates, policy),
                policy_id=policy.policy_id,
            )
        return EffectivePreferenceContext(
            user_id=user_id,
            session_id=session_id,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
            preferences=resolved,
            warnings=warnings,
            readable_domains=readable_domains,
        )

    @staticmethod
    def _index(value: object, ordered: tuple[object, ...]) -> int:
        try:
            return ordered.index(value)
        except ValueError:
            return len(ordered)

    def _rank(self, preference: Preference, policy: ResolutionPolicy) -> tuple[object, ...]:
        ranks: list[object] = []
        for strategy in policy.strategies:
            if strategy is ResolutionStrategy.SOURCE_PRIORITY:
                ranks.append(self._index(preference.source, policy.source_priority))
            elif strategy is ResolutionStrategy.DOMAIN_PRIORITY:
                ranks.append(self._index(preference.owner_domain, policy.domain_priority))
            elif strategy is ResolutionStrategy.EXPLICIT_OVER_INFERRED:
                ranks.append(0 if preference.confirmed else 1)
            elif strategy is ResolutionStrategy.MOST_RECENT:
                timestamp = preference.updated_at or datetime.min.replace(tzinfo=UTC)
                ranks.append(-timestamp.timestamp())
            elif strategy is ResolutionStrategy.HIGHEST_CONFIDENCE:
                ranks.append(-(preference.confidence if preference.confidence is not None else 1.0))
        provenance = str(sorted(preference.provenance.items()))
        return (*ranks, preference.key, provenance)

    def _reason(
        self,
        selected: Preference,
        candidates: list[Preference],
        policy: ResolutionPolicy,
    ) -> str:
        if selected.source is PreferenceSource.SESSION_OVERRIDE:
            return "SESSION_OVERRIDE"
        if policy.domain_priority and selected.owner_domain == policy.domain_priority[0]:
            return "DOMAIN_AUTHORITY"
        if selected.source is PreferenceSource.EXPLICIT_PROFILE:
            return "EXPLICIT_PROFILE_PRIORITY"
        if selected.source is PreferenceSource.MEMORY_PROFILE:
            return "CANONICAL_MEMORY_PROFILE"
        if len(candidates) > 1:
            return "POLICY_RANKED"
        return "ONLY_ELIGIBLE_VALUE"

