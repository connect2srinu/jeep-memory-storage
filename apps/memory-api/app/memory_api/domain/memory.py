from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryScope:
    user_id: str
    app_name: str
    domain: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.user_id, self.app_name, self.domain)):
            raise ValueError("memory scope values must be non-empty")

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.user_id, self.app_name, self.domain


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
