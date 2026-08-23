from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class AccessPermission(StrEnum):
    NONE = "NONE"
    READ = "READ"
    WRITE = "WRITE"
    READ_WRITE = "READ_WRITE"


class AccessRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class AgentRuntimeType(StrEnum):
    ADK_AGENT_RUNTIME = "ADK_AGENT_RUNTIME"
    ADK_CLOUD_RUN = "ADK_CLOUD_RUN"
    ADK_GKE = "ADK_GKE"
    LANGGRAPH_CLOUD_RUN = "LANGGRAPH_CLOUD_RUN"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class MemoryDomain:
    id: str
    name: str
    description: str
    owner_team: str
    owner_contact: str | None
    status: LifecycleStatus = LifecycleStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class ScopeDefinition:
    id: str
    scope_type: str
    scope_keys: tuple[str, ...]
    description: str
    owner_domain_id: str
    status: LifecycleStatus = LifecycleStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class ProfileSchema:
    id: str
    domain_id: str
    display_name: str
    description: str
    owner_team: str
    status: LifecycleStatus = LifecycleStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class RegisteredAgent:
    id: str
    display_name: str
    domain_id: str
    runtime_type: AgentRuntimeType
    identity_type: str
    principal: str | None
    status: LifecycleStatus = LifecycleStatus.ACTIVE
