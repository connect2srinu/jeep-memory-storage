from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import (
    CONTRACT_MODELS,
    ContractDocument,
    DomainContract,
    MemoryConsumersContract,
    MemoryProfilesContract,
    PreferenceCatalogContract,
    ResolutionPoliciesContract,
)


class ContractValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Memory contract validation failed:\n- " + "\n- ".join(errors))


@dataclass(frozen=True, slots=True)
class ContractBundle:
    documents: tuple[ContractDocument, ...]
    source_files: tuple[Path, ...]

    @property
    def domains(self) -> tuple[DomainContract, ...]:
        return tuple(item for item in self.documents if isinstance(item, DomainContract))

    @property
    def catalogs(self) -> tuple[PreferenceCatalogContract, ...]:
        return tuple(
            item for item in self.documents if isinstance(item, PreferenceCatalogContract)
        )

    @property
    def resolutions(self) -> tuple[ResolutionPoliciesContract, ...]:
        return tuple(
            item for item in self.documents if isinstance(item, ResolutionPoliciesContract)
        )

    @property
    def profiles(self) -> tuple[MemoryProfilesContract, ...]:
        return tuple(item for item in self.documents if isinstance(item, MemoryProfilesContract))

    @property
    def consumers(self) -> tuple[MemoryConsumersContract, ...]:
        return tuple(item for item in self.documents if isinstance(item, MemoryConsumersContract))


def _parse_document(path: Path, payload: Any) -> ContractDocument:
    if not isinstance(payload, dict):
        raise ContractValidationError([f"{path}: document must be a YAML mapping"])
    kind = payload.get("kind")
    model = CONTRACT_MODELS.get(str(kind))
    if model is None:
        raise ContractValidationError([f"{path}: unsupported kind {kind!r}"])
    try:
        return model.model_validate(payload)  # type: ignore[return-value]
    except ValidationError as exc:
        errors = [f"{path}: {item['loc']}: {item['msg']}" for item in exc.errors()]
        raise ContractValidationError(errors) from exc


def load_contracts(contracts_dir: Path) -> ContractBundle:
    files = tuple(
        sorted(
            [*contracts_dir.glob("**/*.yaml"), *contracts_dir.glob("**/*.yml")],
            key=lambda item: item.as_posix(),
        )
    )
    if not files:
        raise ContractValidationError([f"no YAML contracts found under {contracts_dir}"])

    documents: list[ContractDocument] = []
    errors: list[str] = []
    for path in files:
        try:
            with path.open(encoding="utf-8") as stream:
                payloads = list(yaml.safe_load_all(stream))
            for payload in payloads:
                if payload is not None:
                    documents.append(_parse_document(path, payload))
        except (yaml.YAMLError, ContractValidationError) as exc:
            if isinstance(exc, ContractValidationError):
                errors.extend(exc.errors)
            else:
                errors.append(f"{path}: invalid YAML: {exc}")
    if errors:
        raise ContractValidationError(errors)

    bundle = ContractBundle(tuple(documents), files)
    _validate_cross_references(bundle)
    return bundle


def _validate_cross_references(bundle: ContractBundle) -> None:
    errors: list[str] = []
    domains: dict[str, DomainContract] = {}
    for contract in bundle.domains:
        name = str(contract.metadata.name)
        if name in domains:
            errors.append(f"duplicate MemoryDomain: {name}")
        domains[name] = contract

    preferences = {}
    for catalog in bundle.catalogs:
        catalog_domain = str(catalog.metadata.domain)
        if catalog_domain not in domains:
            errors.append(f"PreferenceCatalog references unknown domain: {catalog_domain}")
        for preference in catalog.preferences:
            if preference.key in preferences:
                errors.append(f"duplicate preference key: {preference.key}")
            preferences[preference.key] = preference
            if preference.owner_domain != catalog_domain:
                errors.append(
                    f"{preference.key}: ownerDomain must match catalog domain {catalog_domain}"
                )
            for domain in [*preference.allowed_readers, *preference.allowed_writers]:
                if domain not in domains:
                    errors.append(f"{preference.key}: unknown allowed domain {domain}")
            if preference.owner_domain not in preference.allowed_writers:
                errors.append(f"{preference.key}: owner domain must be an allowed writer")

    for name, contract in domains.items():
        for referenced in [*contract.spec.permissions.read, *contract.spec.permissions.write]:
            if referenced not in domains:
                errors.append(f"domain {name}: permission references unknown domain {referenced}")
        if name not in contract.spec.permissions.read or name not in contract.spec.permissions.write:
            errors.append(f"domain {name}: must be able to read and write its own domain")
        if contract.spec.isolation == "strict" and (
            contract.spec.permissions.read != [name] or contract.spec.permissions.write != [name]
        ):
            errors.append(f"domain {name}: strict isolation permits only its own domain")

    policy_ids: dict[str, Any] = {}
    default_count = 0
    for contract in bundle.resolutions:
        if contract.defaults is not None:
            default_count += 1
        for policy in contract.policies:
            if policy.id in policy_ids:
                errors.append(f"duplicate resolution policy: {policy.id}")
            policy_ids[policy.id] = policy
            for key in policy.applies_to:
                if key not in preferences:
                    errors.append(f"policy {policy.id}: unknown preference {key}")
            for domain in policy.domain_priority or []:
                if domain not in domains:
                    errors.append(f"policy {policy.id}: unknown domain priority {domain}")
    if default_count != 1:
        errors.append("exactly one resolution policy document must define defaults")
    for preference in preferences.values():
        if preference.resolution_policy not in policy_ids:
            errors.append(
                f"{preference.key}: unknown resolution policy {preference.resolution_policy}"
            )

    profiles = {}
    for contract in bundle.profiles:
        for profile in contract.profiles:
            if profile.id in profiles:
                errors.append(f"duplicate Memory Profile ID: {profile.id}")
            profiles[profile.id] = profile
            if profile.owner_domain not in domains:
                errors.append(f"profile {profile.id}: unknown owner domain {profile.owner_domain}")
            expected_scope = domains[profile.owner_domain].spec.scopes.profile_scope_keys
            if profile.scope_keys != expected_scope:
                errors.append(
                    f"profile {profile.id}: scopeKeys must match domain profileScopeKeys"
                )
            for field in profile.fields:
                preference = preferences.get(field.preference)
                if preference is None:
                    errors.append(f"profile {profile.id}: unknown preference {field.preference}")
                elif preference.owner_domain != profile.owner_domain:
                    errors.append(
                        f"profile {profile.id}: {field.preference} belongs to another domain"
                    )
                elif not preference.canonical:
                    errors.append(
                        f"profile {profile.id}: dynamic preference {field.preference} is not allowed"
                    )
    for preference in preferences.values():
        if preference.profile and preference.profile not in profiles:
            errors.append(f"{preference.key}: unknown profile {preference.profile}")

    agent_ids: set[str] = set()
    for contract in bundle.consumers:
        for consumer in contract.consumers:
            if consumer.agent_id in agent_ids:
                errors.append(f"duplicate consumer agentId: {consumer.agent_id}")
            agent_ids.add(consumer.agent_id)
            domain = domains.get(consumer.consumer_domain)
            if domain is None:
                errors.append(
                    f"consumer {consumer.agent_id}: unknown domain {consumer.consumer_domain}"
                )
                continue
            for key in consumer.required_preferences:
                preference = preferences.get(key)
                if preference is None:
                    errors.append(f"consumer {consumer.agent_id}: unknown preference {key}")
                elif preference.owner_domain not in domain.spec.permissions.read:
                    errors.append(f"consumer {consumer.agent_id}: domain cannot read {key}")
                elif consumer.consumer_domain not in preference.allowed_readers:
                    errors.append(f"consumer {consumer.agent_id}: catalog does not allow {key}")

    if errors:
        raise ContractValidationError(errors)
