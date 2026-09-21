from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryScope:
    organization_id: str
    user_id: str
    # Optional sub-entity partition (e.g. a member's dependent/child). None = member-level scope.
    dependent_id: str | None = None

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.organization_id, self.user_id)):
            raise ValueError("memory scope values must be non-empty")
        if self.dependent_id is not None and not self.dependent_id.strip():
            raise ValueError("dependent_id, when provided, must be non-empty")

    @property
    def identity(self) -> tuple[str, ...]:
        if self.dependent_id is None:
            return self.organization_id, self.user_id
        return self.organization_id, self.user_id, self.dependent_id


@dataclass(frozen=True, slots=True)
class MemoryProfileSchema:
    id: str
    domain: str
    version: str
    fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class MemoryProfile:
    schema_id: str
    scope: MemoryScope
    values: dict[str, Any]
    version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class PreferenceWrite:
    schema_id: str
    attribute: str
    value: Any


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    text: str
    candidates: tuple[PreferenceWrite, ...] = ()
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class NaturalMemory:
    id: str
    scope: MemoryScope
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GenerationResult:
    natural_memory: NaturalMemory
    updated_profiles: tuple[MemoryProfile, ...]


@dataclass(frozen=True, slots=True)
class DynamicMemory:
    """A non-canonical memory retained only within an approved topic boundary."""

    scope: MemoryScope
    topic: str
    value: Any
    confidence: float
    version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    sensitivity: str | None = None
    source: str | None = None
