from __future__ import annotations

from dataclasses import dataclass, field
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
    # attribute_id -> catalog sensitivity classification (normal | sensitive | restricted).
    attribute_sensitivity: dict[str, str] = field(default_factory=dict)
    # attribute_id -> catalog description ("meaning"), surfaced to help the agent map statements.
    attribute_descriptions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HouseholdMember:
    """An active member of a household (the account holder or a no-login dependent)."""

    member_id: str
    display_name: str | None
    relationship: str
    has_login: bool
    is_guardian: bool


@dataclass(frozen=True, slots=True)
class RuntimeResolutionConfig:
    policy_id: str
    version: str
    defaults: dict[str, Any]
    attribute_rules: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RuntimeDynamicPolicy:
    """Governs non-canonical (dynamic) memory for a domain: which topics may be persisted."""

    policy_id: str
    domain_id: str
    enabled: bool
    approved_topics: tuple[str, ...]
    confidence_threshold: float
    confirmation_required: bool
    retention_days: int | None = None
    # topic -> declared sensitivity tier (normal | sensitive | restricted); absent means normal.
    topic_sensitivity: dict[str, str] = field(default_factory=dict)
    # topic -> domain-specific description ("meaning") of what the topic covers.
    topic_descriptions: dict[str, str] = field(default_factory=dict)
