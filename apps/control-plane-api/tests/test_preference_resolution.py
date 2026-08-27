from __future__ import annotations

from datetime import UTC, datetime, timedelta

from control_plane_api.domain.preferences import Preference, PreferenceSource
from control_plane_api.domain.resolution import (
    DomainAccessPolicy,
    PreferenceCatalog,
    PreferenceDefinition,
    ResolutionPolicy,
    ResolutionPolicyRegistry,
    ResolutionStrategy,
)
from control_plane_api.services.preference_resolver import PreferenceResolver


def components(
    minimum_confidence: float = 0.7,
) -> tuple[PreferenceCatalog, ResolutionPolicyRegistry]:
    catalog = PreferenceCatalog(
        (
            PreferenceDefinition(
                "customer.diet", "customer", "diet", ("customer", "grocery"), ("customer",)
            ),
            PreferenceDefinition(
                "grocery.diet_override", "grocery", "diet", ("grocery",), ("grocery",)
            ),
            PreferenceDefinition(
                "grocery.preferred_snack",
                "grocery",
                "preferred_snack",
                ("grocery",),
                ("grocery",),
            ),
        )
    )
    default = ResolutionPolicy(
        id="default-v1",
        source_priority=(
            PreferenceSource.SESSION_OVERRIDE,
            PreferenceSource.EXPLICIT_PROFILE,
            PreferenceSource.MEMORY_PROFILE,
            PreferenceSource.DYNAMIC_MEMORY,
            PreferenceSource.DEFAULT,
        ),
        domain_priority=("grocery", "customer"),
        strategies=(
            ResolutionStrategy.SOURCE_PRIORITY,
            ResolutionStrategy.DOMAIN_PRIORITY,
            ResolutionStrategy.EXPLICIT_OVER_INFERRED,
            ResolutionStrategy.MOST_RECENT,
        ),
        minimum_confidence=minimum_confidence,
    )
    registry = ResolutionPolicyRegistry(
        domain_policies=(
            DomainAccessPolicy("grocery", ("grocery", "customer"), ("grocery",)),
            DomainAccessPolicy("customer", ("customer",), ("customer",)),
        ),
        policies={},
        default_policy=default,
        version="test-v1",
    )
    return catalog, registry


def resolve(values: list[Preference], minimum_confidence: float = 0.7):
    catalog, policies = components(minimum_confidence)
    return PreferenceResolver(catalog, policies).resolve(
        user_id="u1",
        session_id="s1",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        preferences=values,
        readable_domains=policies.domain_policy("grocery").readable_domains,
    )


def preference(
    key: str,
    value: object,
    source: PreferenceSource,
    domain: str = "grocery",
    **kwargs: object,
) -> Preference:
    return Preference(
        key=key,
        value=value,
        source=source,
        owner_domain=domain,
        updated_at=datetime.now(UTC),
        **kwargs,
    )


def test_source_priority_and_provenance_are_deterministic() -> None:
    snapshot = resolve(
        [
            preference("grocery.preferred_snack", "chips", PreferenceSource.MEMORY_PROFILE),
            preference(
                "grocery.preferred_snack",
                "fruit",
                PreferenceSource.SESSION_OVERRIDE,
                provenance={"event": "e1"},
            ),
        ]
    )
    selected = snapshot.preferences["preferred_snack"]
    assert selected.preference.value == "fruit"
    assert selected.preference.provenance == {"event": "e1"}
    assert selected.resolution_reason == "SESSION_OVERRIDE"
    assert snapshot.policy_version == "test-v1"


def test_logical_attribute_resolution_preserves_domain_authority() -> None:
    snapshot = resolve(
        [
            preference("customer.diet", "vegetarian", PreferenceSource.MEMORY_PROFILE, "customer"),
            preference("grocery.diet_override", "none", PreferenceSource.MEMORY_PROFILE),
        ]
    )
    assert snapshot.preferences["diet"].preference.owner_domain == "grocery"
    assert snapshot.preferences["diet"].resolution_reason == "DOMAIN_AUTHORITY"


def test_expired_low_confidence_and_unreadable_values_are_filtered() -> None:
    snapshot = resolve(
        [
            preference(
                "grocery.preferred_snack",
                "expired",
                PreferenceSource.SESSION_OVERRIDE,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            preference(
                "grocery.preferred_snack",
                "uncertain",
                PreferenceSource.DYNAMIC_MEMORY,
                confidence=0.5,
            ),
            preference(
                "pharmacy.medication", "hidden", PreferenceSource.EXPLICIT_PROFILE, "pharmacy"
            ),
        ]
    )
    assert snapshot.preferences == {}
