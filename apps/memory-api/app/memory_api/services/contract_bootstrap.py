from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from memory_api.persistence.models import (
    AgentSchemaGrantRecord,
    AuditEventRecord,
    DynamicMemoryPolicyRecord,
    MemoryDomainRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    RegisteredAgentRecord,
    ResolutionAttributeOverrideRecord,
    ResolutionPolicyRecord,
    SchemaPreferenceMappingRecord,
    ScopeDefinitionRecord,
)


@dataclass(frozen=True, slots=True)
class ContractBootstrapResult:
    domains: int
    preferences: int
    schemas: int
    agents: int
    grants: int
    policies: int


class ContractBootstrapService:
    """Idempotently materialize validated YAML contracts as active control-plane records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _merge(self, record: Any) -> None:
        await self.session.merge(record)

    async def import_bundle(
        self,
        bundle: Any,
        *,
        actor: str = "contract-bootstrap",
        correlation_id: str = "contract-bootstrap",
    ) -> ContractBootstrapResult:
        domain_contracts = {str(item.metadata.name): item for item in bundle.domains}
        preference_definitions = {
            preference.key: preference
            for catalog in bundle.catalogs
            for preference in catalog.preferences
        }
        profile_definitions = {
            profile.id: profile
            for document in bundle.profiles
            for profile in document.profiles
        }

        for domain_id, contract in domain_contracts.items():
            owner = contract.metadata.owner
            await self._merge(
                MemoryDomainRecord(
                    id=domain_id,
                    name=contract.metadata.display_name or domain_id.replace("-", " ").title(),
                    description=f"Memory domain imported from {domain_id} contract.",
                    owner_team=owner.team if owner else f"{domain_id}-owner",
                    owner_contact=owner.email if owner else None,
                    status="ACTIVE",
                    contract_version=contract.metadata.version,
                )
            )
            scope_id = f"{domain_id}:profile-scope"
            await self._merge(
                ScopeDefinitionRecord(
                    id=scope_id,
                    scope_type="DOMAIN_PROFILE",
                    scope_keys=list(contract.spec.scopes.profile_scope_keys),
                    description=f"Governed profile scope for {domain_id}.",
                    owner_domain_id=domain_id,
                    status="ACTIVE",
                )
            )
            dynamic = contract.spec.dynamic_memory
            defaults = contract.spec.defaults
            await self._merge(
                DynamicMemoryPolicyRecord(
                    id=f"{domain_id}:dynamic:v{contract.metadata.version}",
                    level="DOMAIN",
                    domain_id=domain_id,
                    schema_id=None,
                    enabled=dynamic.enabled,
                    confidence_threshold=dynamic.minimum_confidence,
                    memory_topics=[],
                    retention_policy={
                        "retention_days": defaults.retention_days,
                        "inferred_preference_ttl_days": defaults.inferred_preference_ttl_days,
                        "key_pattern": dynamic.key_pattern,
                    },
                    confirmation_required=dynamic.require_explicit_statement,
                    allowed_dynamic_categories=[],
                    version=contract.metadata.version,
                    status="ACTIVE",
                )
            )

        for key, preference in preference_definitions.items():
            await self._merge(
                PreferenceDefinitionRecord(
                    attribute_id=key,
                    display_name=key.rsplit(".", 1)[-1].replace("_", " ").title(),
                    description=preference.description,
                    data_type=preference.type,
                    allowed_values=list(preference.allowed_values),
                    sensitivity_classification=preference.sensitivity,
                    canonical_owner_id=preference.owner_domain,
                    validation_rules={
                        "scopes": [scope.value for scope in preference.scopes],
                        "allowed_readers": preference.allowed_readers,
                        "allowed_writers": preference.allowed_writers,
                        "confirmation_required_for_long_term": (
                            preference.confirmation.required_for_long_term
                        ),
                        "aliases": preference.aliases,
                    },
                    default_resolution_behavior={"policy": preference.resolution_policy},
                    catalog_version=preference.schema_version,
                )
            )

        for schema_id, profile in profile_definitions.items():
            domain = domain_contracts[profile.owner_domain]
            owner = domain.metadata.owner
            await self._merge(
                ProfileSchemaRecord(
                    id=schema_id,
                    domain_id=profile.owner_domain,
                    display_name=schema_id.replace("-", " ").title(),
                    description=f"Structured profile owned by {profile.owner_domain}.",
                    owner_team=owner.team if owner else f"{profile.owner_domain}-owner",
                    status="ACTIVE",
                )
            )
            version = domain.metadata.version
            schema_version_id = f"{schema_id}:{version}"
            properties = {
                field.profile_field: {
                    "type": preference_definitions[field.preference].type,
                    "description": preference_definitions[field.preference].description,
                }
                for field in profile.fields
            }
            await self._merge(
                ProfileSchemaVersionRecord(
                    id=schema_version_id,
                    schema_id=schema_id,
                    version=version,
                    status="ACTIVE",
                    scope_definition_id=f"{profile.owner_domain}:profile-scope",
                    vertex_schema_definition={
                        "type": "object",
                        "properties": properties,
                        "additionalProperties": False,
                    },
                    generation_config=profile.generation.model_dump(mode="json"),
                )
            )
            for field in profile.fields:
                await self._merge(
                    SchemaPreferenceMappingRecord(
                        id=f"{schema_version_id}:{field.profile_field}",
                        schema_version_id=schema_version_id,
                        attribute_id=field.preference,
                        profile_field=field.profile_field,
                    )
                )

        profile_by_preference = {
            field.preference: profile.id
            for profile in profile_definitions.values()
            for field in profile.fields
        }
        agent_count = 0
        grants: set[tuple[str, str]] = set()
        for document in bundle.consumers:
            for consumer in document.consumers:
                agent_count += 1
                await self._merge(
                    RegisteredAgentRecord(
                        id=consumer.agent_id,
                        display_name=consumer.agent_id.replace("-", " ").title(),
                        domain_id=consumer.consumer_domain,
                        runtime_type="OTHER",
                        identity_type=(
                            "GOOGLE_SERVICE_ACCOUNT" if consumer.service_account else "LOCAL_POC"
                        ),
                        principal=consumer.service_account,
                        capabilities=consumer.capabilities.model_dump(),
                        status="ACTIVE",
                    )
                )
                for preference_key in consumer.required_preferences:
                    schema_id = profile_by_preference.get(preference_key)
                    if schema_id is None or (consumer.agent_id, schema_id) in grants:
                        continue
                    owner_domain = profile_definitions[schema_id].owner_domain
                    permission = (
                        "READ_WRITE" if owner_domain == consumer.consumer_domain else "READ"
                    )
                    await self._merge(
                        AgentSchemaGrantRecord(
                            id=f"{consumer.agent_id}:{schema_id}",
                            agent_id=consumer.agent_id,
                            schema_id=schema_id,
                            permission=permission,
                            status="ACTIVE",
                            approved_by=actor,
                        )
                    )
                    grants.add((consumer.agent_id, schema_id))

        policy_count = 0
        for document in bundle.resolutions:
            domain_id = str(document.metadata.domain or "platform")
            version = document.metadata.version
            policy_id = f"{domain_id}:contract-policy:{version}"
            defaults = document.defaults
            await self._merge(
                ResolutionPolicyRecord(
                    id=policy_id,
                    agent_id=None,
                    name=f"{domain_id} contract policy",
                    version=version,
                    status="ACTIVE",
                    default_rules=defaults.model_dump(mode="json") if defaults else {},
                )
            )
            policy_count += 1
            for policy in document.policies:
                for attribute_id in policy.applies_to:
                    schema_precedence = [
                        profile.id
                        for owner in (policy.domain_priority or [])
                        for profile in profile_definitions.values()
                        if profile.owner_domain == owner
                    ]
                    await self._merge(
                        ResolutionAttributeOverrideRecord(
                            id=f"{policy_id}:{attribute_id}",
                            policy_id=policy_id,
                            attribute_id=attribute_id,
                            schema_precedence=schema_precedence,
                            rules={
                                "source_priority": [
                                    item.value for item in (policy.source_priority or [])
                                ],
                                "strategies": [item.value for item in (policy.strategies or [])],
                                "minimum_confidence": policy.minimum_confidence,
                                "legacy_policy_id": policy.id,
                            },
                        )
                    )

        await self._merge(
            AuditEventRecord(
                id=f"{correlation_id}:contracts-imported",
                actor=actor,
                action="contracts.imported",
                target_type="contract_bundle",
                target_id="config/contracts",
                correlation_id=correlation_id,
                before_metadata=None,
                after_metadata={
                    "domains": len(domain_contracts),
                    "preferences": len(preference_definitions),
                    "schemas": len(profile_definitions),
                    "agents": agent_count,
                },
            )
        )
        await self.session.flush()
        return ContractBootstrapResult(
            domains=len(domain_contracts),
            preferences=len(preference_definitions),
            schemas=len(profile_definitions),
            agents=agent_count,
            grants=len(grants),
            policies=policy_count,
        )
