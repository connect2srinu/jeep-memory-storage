from __future__ import annotations

import pytest
from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.services.authorization import (
    AgentCapability,
    AgentRegistration,
    AuthorizationService,
)
from test_preference_resolution import components


@pytest.fixture
def authorization() -> AuthorizationService:
    catalog, policies = components()
    return AuthorizationService(
        (
            AgentRegistration(
                agent_id="grocery-agent",
                consumer_domain="grocery",
                capabilities=frozenset(
                    {
                        AgentCapability.RESOLVE_CONTEXT,
                        AgentCapability.SUBMIT_CANDIDATES,
                        AgentCapability.INSPECT_PROVENANCE,
                    }
                ),
                schema_grants={
                    "grocery-preferences-v1": AccessPermission.READ_WRITE,
                    "customer-preferences-v1": AccessPermission.READ,
                },
            ),
            AgentRegistration(
                agent_id="grocery-readonly-agent",
                consumer_domain="grocery",
                capabilities=frozenset({AgentCapability.RESOLVE_CONTEXT}),
                schema_grants={"grocery-preferences-v1": AccessPermission.READ},
            ),
        ),
        catalog,
        policies,
    )


def test_registered_agent_capability_and_schema_grants(authorization: AuthorizationService) -> None:
    registration = authorization.require_capability(
        "grocery-agent", "grocery", AgentCapability.RESOLVE_CONTEXT
    )
    authorization.require_schema_access(
        registration, "customer-preferences-v1", AccessPermission.READ
    )
    with pytest.raises(PermissionError, match="lacks WRITE"):
        authorization.require_schema_access(
            registration, "customer-preferences-v1", AccessPermission.WRITE
        )


def test_unknown_domain_mismatch_and_missing_capability_are_denied(
    authorization: AuthorizationService,
) -> None:
    with pytest.raises(PermissionError, match="not registered"):
        authorization.require_capability("unknown", "grocery", AgentCapability.RESOLVE_CONTEXT)
    with pytest.raises(PermissionError, match="does not match"):
        authorization.require_capability(
            "grocery-agent", "delivery", AgentCapability.RESOLVE_CONTEXT
        )
    with pytest.raises(PermissionError, match="lacks capability submit_candidates"):
        authorization.require_capability(
            "grocery-readonly-agent", "grocery", AgentCapability.SUBMIT_CANDIDATES
        )


def test_domain_and_catalog_rules_prevent_cross_domain_write(
    authorization: AuthorizationService,
) -> None:
    authorization.require_attribute_access("grocery", "customer.diet", write=False)
    with pytest.raises(PermissionError, match="write is not allowed"):
        authorization.require_attribute_access("grocery", "customer.diet", write=True)
    with pytest.raises(PermissionError, match="not registered"):
        authorization.require_attribute_access("grocery", "grocery.unknown", write=True)
