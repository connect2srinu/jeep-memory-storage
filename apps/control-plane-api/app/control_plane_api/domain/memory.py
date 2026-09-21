from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# The optional scope keys beyond organization_id, in canonical order. A scope is org + any subset,
# supporting member ({user_id}), household-shared ({household_id}), and household-member
# ({household_id, member_id}) partitions.
_SCOPE_KEY_ORDER = ("user_id", "household_id", "member_id")


@dataclass(frozen=True, slots=True)
class MemoryScope:
    organization_id: str
    user_id: str | None = None
    household_id: str | None = None
    member_id: str | None = None

    def __post_init__(self) -> None:
        if not self.organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        for key in _SCOPE_KEY_ORDER:
            value = getattr(self, key)
            if value is not None and not value.strip():
                raise ValueError(f"{key}, when provided, must be non-empty")
        if not any(getattr(self, key) is not None for key in _SCOPE_KEY_ORDER):
            raise ValueError("memory scope requires at least one key beyond organization_id")

    @property
    def keys(self) -> tuple[tuple[str, str], ...]:
        """The present scope keys (name, value) beyond organization_id, in canonical order."""
        return tuple(
            (key, getattr(self, key))
            for key in _SCOPE_KEY_ORDER
            if getattr(self, key) is not None
        )

    @property
    def identity(self) -> tuple[str, ...]:
        return (self.organization_id, *(value for _, value in self.keys))

    def as_dict(self) -> dict[str, str]:
        return {"organization_id": self.organization_id, **dict(self.keys)}


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
