from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loader import ContractBundle
from .models import CONTRACT_MODELS


@dataclass(frozen=True, slots=True)
class CompilationResult:
    artifacts: dict[Path, str]

    def write(self, project_root: Path) -> None:
        for relative_path, content in self.artifacts.items():
            path = project_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def differences(self, project_root: Path) -> list[str]:
        differences = []
        for relative_path, expected in self.artifacts.items():
            path = project_root / relative_path
            if not path.exists():
                differences.append(f"missing generated artifact: {relative_path}")
            elif path.read_text(encoding="utf-8") != expected:
                differences.append(f"stale generated artifact: {relative_path}")
        return differences


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def compile_contracts(bundle: ContractBundle) -> CompilationResult:
    domain_payload: dict[str, Any] = {"version": "1.0", "domains": {}}
    for contract in sorted(bundle.domains, key=lambda item: str(item.metadata.name)):
        name = str(contract.metadata.name)
        domain_payload["domains"][name] = {
            "read": contract.spec.permissions.read,
            "write": contract.spec.permissions.write,
            "isolation": contract.spec.isolation,
        }

    preference_definitions = {
        preference.key: preference
        for catalog in bundle.catalogs
        for preference in catalog.preferences
    }
    catalog_payload: dict[str, Any] = {"version": "1.0", "preferences": {}}
    for key, preference in sorted(preference_definitions.items()):
        item: dict[str, Any] = {
            "type": preference.type,
            "owner_domain": preference.owner_domain,
            "description": preference.description,
            "canonical": preference.canonical,
            "sensitivity": preference.sensitivity,
            "scopes": [scope.value for scope in preference.scopes],
            "schema_version": preference.schema_version,
            "allowed_readers": preference.allowed_readers,
            "allowed_writers": preference.allowed_writers,
            "resolution_policy": preference.resolution_policy,
            "aliases": preference.aliases,
        }
        if preference.allowed_values:
            item["allowed_values"] = preference.allowed_values
        if preference.lifecycle.session_ttl_seconds:
            item["ttl_seconds"] = preference.lifecycle.session_ttl_seconds
        catalog_payload["preferences"][key] = item

    default_contract = next(item for item in bundle.resolutions if item.defaults is not None)
    defaults = default_contract.defaults
    assert defaults is not None
    resolution_payload: dict[str, Any] = {
        "version": "1.0",
        "default": {
            "source_priority": [source.value for source in defaults.source_priority],
            "domain_priority": defaults.domain_priority,
            "strategies": [strategy.value for strategy in defaults.strategies],
            "minimum_confidence": defaults.minimum_confidence,
        },
        "policies": {},
    }
    for contract in bundle.resolutions:
        for policy in contract.policies:
            item: dict[str, Any] = {}
            if policy.source_priority is not None:
                item["source_priority"] = [source.value for source in policy.source_priority]
            if policy.domain_priority is not None:
                item["domain_priority"] = policy.domain_priority
            if policy.strategies is not None:
                item["strategies"] = [strategy.value for strategy in policy.strategies]
            if policy.minimum_confidence is not None:
                item["minimum_confidence"] = policy.minimum_confidence
            resolution_payload["policies"][policy.id] = item

    grouped_profiles: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    profile_manifest: dict[str, Any] = {"version": "1.0", "profiles": {}}
    profile_registry: dict[str, Any] = {}
    for contract in bundle.profiles:
        for profile in contract.profiles:
            properties = {}
            field_mappings = {}
            for field in profile.fields:
                preference = preference_definitions[field.preference]
                schema: dict[str, Any] = {
                    "type": preference.type,
                    "description": preference.description,
                }
                if preference.allowed_values:
                    schema["enum"] = preference.allowed_values
                properties[field.profile_field] = schema
                field_mappings[field.profile_field] = field.preference
            schema_config = {
                "id": profile.id,
                "memory_schema": {
                    "type": "object",
                    "description": f"Canonical preferences owned by {profile.owner_domain}.",
                    "properties": properties,
                    "additionalProperties": False,
                },
            }
            grouped_profiles.setdefault(tuple(profile.scope_keys), []).append(schema_config)
            profile_manifest["profiles"][profile.id] = {
                "owner_domain": profile.owner_domain,
                "scope_keys": profile.scope_keys,
                "fields": field_mappings,
                "generation": profile.generation.model_dump(by_alias=False, mode="json"),
            }
            profile_registry[profile.id] = {
                "owner_domain": profile.owner_domain,
                "fields": field_mappings,
            }
    structured_configs = [
        {
            "scope_keys": list(scope_keys),
            "schema_configs": sorted(schema_configs, key=lambda item: item["id"]),
        }
        for scope_keys, schema_configs in sorted(grouped_profiles.items())
    ]
    memory_profile_payload = {
        "version": "1.0",
        "profile_registry": profile_registry,
        "structured_memory_configs": structured_configs,
    }

    consumers_payload: dict[str, Any] = {"version": "1.0", "consumers": {}}
    for contract in bundle.consumers:
        for consumer in contract.consumers:
            consumers_payload["consumers"][consumer.agent_id] = {
                "consumer_domain": consumer.consumer_domain,
                "service_account": consumer.service_account,
                "required_preferences": consumer.required_preferences,
                "capabilities": consumer.capabilities.model_dump(by_alias=False),
            }

    schema_payloads = {
        f"config/schemas/{kind}.schema.json": _json(model.model_json_schema(by_alias=True))
        for kind, model in CONTRACT_MODELS.items()
    }
    artifacts = {
        Path("app/shared_memory/catalog/catalog.json"): _json(catalog_payload),
        Path("app/shared_memory/policies/domain_policy.json"): _json(domain_payload),
        Path("app/shared_memory/policies/resolution_policy.json"): _json(
            resolution_payload
        ),
        Path("app/shared_memory/profiles/memory_profiles.json"): _json(
            memory_profile_payload
        ),
        Path("app/shared_memory/contracts/consumers.json"): _json(consumers_payload),
        Path("config/generated/profile_manifest.json"): _json(profile_manifest),
        **{Path(path): content for path, content in schema_payloads.items()},
    }
    return CompilationResult(artifacts)
