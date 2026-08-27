from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from control_plane_api.domain.control_plane import AccessPermission


@dataclass(frozen=True, slots=True)
class RuntimeAgent:
    id: str
    organization_id: str
    project_id: str
    domain_id: str
    principal: str | None
    capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class RuntimeSchemaGrant:
    schema_id: str
    owner_organization_id: str
    domain_id: str
    schema_version: str
    permission: AccessPermission
    scope_keys: tuple[str, ...]
    field_to_attribute: dict[str, str]


@dataclass(frozen=True, slots=True)
class RuntimeResolutionConfig:
    policy_id: str
    version: str
    defaults: dict[str, Any]
    attribute_rules: dict[str, dict[str, Any]]
