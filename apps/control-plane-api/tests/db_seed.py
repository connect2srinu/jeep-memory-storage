from __future__ import annotations

from datetime import UTC, datetime

from control_plane_api.persistence import Database
from control_plane_api.persistence.models import (
    AgentSchemaGrantRecord,
    AuditEventRecord,
    DynamicMemoryPolicyRecord,
    MemoryDomainRecord,
    OrganizationMembershipRecord,
    OrganizationRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    ProjectMembershipRecord,
    ProjectRecord,
    RegisteredAgentRecord,
    ResolutionAttributeOverrideRecord,
    ResolutionPolicyRecord,
    SchemaPreferenceMappingRecord,
    ScopeDefinitionRecord,
)

PREFERENCES = {
    "customer": {
        "fulfillment_preference": "string",
        "preferred_store": "string",
        "diet": "string",
        "fruit": "string",
    },
    "grocery": {
        "preferred_store": "string",
        "dietary_preference": "string",
        "allow_substitutions": "boolean",
        "organic_preference": "boolean",
        "preferred_brand": "string",
        "preferred_milk": "string",
        "preferred_product_type": "string",
        "preferred_snack": "string",
    },
    "inventory": {"preferred_store": "string"},
    "delivery": {"preferred_window": "string"},
    "store": {"preferred_product_type": "string"},
}

AGENTS = {
    "customer-agent": ("customer", True, True),
    "grocery-agent": ("grocery", True, True),
    "grocery-readonly-agent": ("grocery", False, False),
    "inventory-agent": ("inventory", True, True),
    "delivery-agent": ("delivery", True, True),
    "store-agent": ("store", True, True),
}

# Approved dynamic-memory topics per domain (empty for domains that only use canonical memory).
# An entry may declare a sensitivity tier as "topic:tier" (e.g. "wellness:sensitive").
DYNAMIC_TOPICS = {"grocery": ["shopping", "fulfillment", "wellness:sensitive"]}

GRANTS = {
    "customer-agent": {"customer": "READ_WRITE"},
    "grocery-agent": {
        "grocery": "READ_WRITE",
        "customer": "READ",
        "inventory": "READ",
        "delivery": "READ",
        "store": "READ",
    },
    "grocery-readonly-agent": {"grocery": "READ_WRITE", "customer": "READ"},
    "inventory-agent": {"inventory": "READ_WRITE"},
    "delivery-agent": {
        "delivery": "READ_WRITE",
        "customer": "READ",
        "grocery": "READ",
    },
    "store-agent": {"store": "READ_WRITE", "customer": "READ", "grocery": "READ"},
}


async def seed_control_plane(database: Database) -> None:
    """Create deterministic active records through the normalized database model.

    Production starts empty and is configured through the Admin API/UI. These records exist only
    to keep API tests focused on authorization and resolution instead of repeating onboarding.
    """

    now = datetime.now(UTC)
    async with database.session() as session:
        await session.merge(
            OrganizationRecord(
                id="retail",
                name="Retail",
                description="Test-only retail organization.",
                status="ACTIVE",
            )
        )
        for project_id, name, team in (
            ("shopping", "Shopping", "shopping-platform"),
            ("customer-experience", "Customer Experience", "customer-platform"),
        ):
            await session.merge(
                ProjectRecord(
                    id=project_id,
                    organization_id="retail",
                    name=name,
                    description=f"Test-only {name} project.",
                    owner_team=team,
                    status="ACTIVE",
                )
            )
        await session.merge(
            OrganizationMembershipRecord(
                id="retail:platform-admin",
                organization_id="retail",
                member_principal="platform@example.com",
                display_name="Platform Administrator",
                role="OWNER",
                status="ACTIVE",
            )
        )
        await session.merge(
            ProjectMembershipRecord(
                id="shopping:platform-admin",
                project_id="shopping",
                member_principal="platform@example.com",
                display_name="Platform Administrator",
                role="OWNER",
                status="ACTIVE",
            )
        )
        for domain in (*PREFERENCES, "pharmacy"):
            project_id = "customer-experience" if domain == "customer" else "shopping"
            await session.merge(
                MemoryDomainRecord(
                    id=domain,
                    organization_id="retail",
                    project_id=project_id,
                    name=domain.title(),
                    description=f"Test-only {domain} memory domain.",
                    owner_team=f"{domain}-platform",
                    status="ACTIVE",
                    contract_version="1.0",
                )
            )
            await session.merge(
                ScopeDefinitionRecord(
                    id=f"{domain}:profile-scope",
                    scope_type="DOMAIN_PROFILE",
                    scope_keys=["organization_id", "user_id"],
                    description=f"Test-only scope for {domain}.",
                    owner_domain_id=domain,
                    status="ACTIVE",
                )
            )
            await session.merge(
                DynamicMemoryPolicyRecord(
                    id=f"{domain}:test-dynamic:1",
                    level="DOMAIN",
                    domain_id=domain,
                    enabled=domain not in {"customer", "inventory", "pharmacy"},
                    confidence_threshold=0.7,
                    memory_topics=list(DYNAMIC_TOPICS.get(domain, [])),
                    retention_policy={"retention_days": 365},
                    confirmation_required=True,
                    allowed_dynamic_categories=[],
                    version="1",
                    status="ACTIVE",
                )
            )

        for domain, fields in PREFERENCES.items():
            for field, data_type in fields.items():
                attribute = f"{domain}.{field}"
                await session.merge(
                    PreferenceDefinitionRecord(
                        attribute_id=attribute,
                        display_name=field.replace("_", " ").title(),
                        description=f"Test-only definition for {attribute}.",
                        data_type=data_type,
                        allowed_values=[],
                        sensitivity_classification=(
                            "sensitive"
                            if attribute
                            in {"customer.diet", "customer.fruit", "grocery.dietary_preference"}
                            else "normal"
                        ),
                        canonical_owner_id=domain,
                        validation_rules={"aliases": [field]},
                        default_resolution_behavior={"policy": field},
                        catalog_version="1",
                    )
                )

            schema_id = f"{domain}-preferences-v1"
            version_id = f"{schema_id}:1.0"
            await session.merge(
                ProfileSchemaRecord(
                    id=schema_id,
                    domain_id=domain,
                    display_name=f"{domain.title()} Preferences",
                    description=f"Test-only structured profile for {domain}.",
                    owner_team=f"{domain}-platform",
                    status="ACTIVE",
                )
            )
            await session.merge(
                ProfileSchemaVersionRecord(
                    id=version_id,
                    schema_id=schema_id,
                    version="1.0",
                    status="ACTIVE",
                    scope_definition_id=f"{domain}:profile-scope",
                    vertex_schema_definition={
                        "type": "object",
                        "properties": {
                            field: {"type": "boolean" if kind == "boolean" else "string"}
                            for field, kind in fields.items()
                        },
                        "additionalProperties": False,
                    },
                    generation_config={"enabled": domain != "inventory"},
                )
            )
            for field in fields:
                await session.merge(
                    SchemaPreferenceMappingRecord(
                        id=f"{version_id}:{field}",
                        schema_version_id=version_id,
                        attribute_id=f"{domain}.{field}",
                        profile_field=field,
                    )
                )

        for agent_id, (domain, submit, provenance) in AGENTS.items():
            project_id = "customer-experience" if domain == "customer" else "shopping"
            await session.merge(
                RegisteredAgentRecord(
                    id=agent_id,
                    display_name=agent_id.replace("-", " ").title(),
                    organization_id="retail",
                    project_id=project_id,
                    domain_id=domain,
                    runtime_type="OTHER",
                    identity_type="LOCAL_POC",
                    capabilities={
                        "resolve_context": True,
                        "submit_candidates": submit,
                        "inspect_provenance": provenance,
                        "administer_memory": agent_id == "grocery-agent",
                    },
                    status="ACTIVE",
                )
            )

        for agent_id, grants in GRANTS.items():
            for domain, permission in grants.items():
                schema_id = f"{domain}-preferences-v1"
                await session.merge(
                    AgentSchemaGrantRecord(
                        id=f"{agent_id}:{schema_id}",
                        agent_id=agent_id,
                        schema_id=schema_id,
                        permission=permission,
                        status="ACTIVE",
                        approved_by="test-seed",
                        approved_at=now,
                    )
                )

        defaults = {
            "source_priority": [
                "SESSION_OVERRIDE",
                "EXPLICIT_PROFILE",
                "MEMORY_PROFILE",
                "DOMAIN_MEMORY",
                "DYNAMIC_MEMORY",
                "INFERRED_MEMORY",
                "DEFAULT",
            ],
            "domain_priority": [],
            "strategies": [
                "SOURCE_PRIORITY",
                "DOMAIN_PRIORITY",
                "EXPLICIT_OVER_INFERRED",
                "MOST_RECENT",
                "HIGHEST_CONFIDENCE",
            ],
            "minimum_confidence": 0.7,
        }
        for domain in PREFERENCES:
            await session.merge(
                ResolutionPolicyRecord(
                    id=f"{domain}:test-policy:1",
                    agent_id=None,
                    name=f"{domain.title()} test policy",
                    version="1.0",
                    status="ACTIVE",
                    default_rules=defaults,
                )
            )

        grocery_policy = "grocery:test-policy:1"
        for attribute in (
            "customer.preferred_store",
            "grocery.preferred_store",
            "inventory.preferred_store",
        ):
            await session.merge(
                ResolutionAttributeOverrideRecord(
                    id=f"{grocery_policy}:{attribute}",
                    policy_id=grocery_policy,
                    attribute_id=attribute,
                    schema_precedence=[
                        "customer-preferences-v1",
                        "grocery-preferences-v1",
                        "inventory-preferences-v1",
                    ],
                    rules={"minimum_confidence": 0.7},
                )
            )

        await session.merge(
            AuditEventRecord(
                id="test-seed:control-plane",
                actor="test-seed",
                action="test.control_plane.seeded",
                target_type="database_fixture",
                target_id="normalized-control-plane",
                correlation_id="test-seed",
                before_metadata=None,
                after_metadata={
                    "domains": len(PREFERENCES) + 1,
                    "preferences": sum(len(fields) for fields in PREFERENCES.values()),
                },
            )
        )
