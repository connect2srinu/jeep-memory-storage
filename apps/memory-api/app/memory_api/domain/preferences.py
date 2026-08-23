from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class PreferenceSource(StrEnum):
    SESSION_OVERRIDE = "SESSION_OVERRIDE"
    EXPLICIT_PROFILE = "EXPLICIT_PROFILE"
    MEMORY_PROFILE = "MEMORY_PROFILE"
    DOMAIN_MEMORY = "DOMAIN_MEMORY"
    DYNAMIC_MEMORY = "DYNAMIC_MEMORY"
    INFERRED_MEMORY = "INFERRED_MEMORY"
    DEFAULT = "DEFAULT"


@dataclass(frozen=True, slots=True)
class Preference:
    key: str
    value: Any
    source: PreferenceSource
    owner_domain: str
    confidence: float | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None
    confirmed: bool = True
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.owner_domain.strip():
            raise ValueError("preference key and owner domain are required")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if any(value is not None and value.tzinfo is None for value in (self.updated_at, self.expires_at)):
            raise ValueError("timestamps must be timezone-aware")

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ResolvedPreference:
    preference: Preference
    resolution_reason: str
    policy_id: str


@dataclass(frozen=True, slots=True)
class EffectivePreferenceSnapshot:
    user_id: str
    session_id: str
    consumer_domain: str
    agent_id: str
    preferences: dict[str, ResolvedPreference]
    readable_domains: tuple[str, ...]
    policy_version: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
