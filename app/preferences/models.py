from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class PreferenceSource(StrEnum):
    SESSION_OVERRIDE = "SESSION_OVERRIDE"
    EXPLICIT_PROFILE = "EXPLICIT_PROFILE"
    LONG_TERM_MEMORY = "LONG_TERM_MEMORY"
    DEFAULT = "DEFAULT"


class PreferenceScope(StrEnum):
    SESSION = "SESSION"
    USER = "USER"


@dataclass(frozen=True, slots=True)
class Preference:
    key: str
    value: Any
    source: PreferenceSource
    domain: str = "customer.grocery"
    scope: PreferenceScope = PreferenceScope.USER
    confidence: float | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("preference key must be non-empty")
        if not self.domain or not self.domain.strip():
            raise ValueError("preference domain must be non-empty")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        for timestamp in (self.updated_at, self.expires_at):
            if timestamp is not None and timestamp.tzinfo is None:
                raise ValueError("timestamps must be timezone-aware")

    def is_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return self.expires_at is not None and self.expires_at <= current

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source"] = self.source.value
        result["scope"] = self.scope.value
        for field_name in ("updated_at", "expires_at"):
            value = result[field_name]
            result[field_name] = value.isoformat() if value else None
        return result


@dataclass(frozen=True, slots=True)
class EffectivePreferenceContext:
    user_id: str
    session_id: str
    agent_id: str
    domain: str
    preferences: dict[str, Preference]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "preferences": {
                key: preference.public_dict()
                for key, preference in sorted(self.preferences.items())
            },
            "generated_at": self.generated_at.isoformat(),
            "warnings": list(self.warnings),
        }

    def for_prompt(self) -> str:
        """Return only resolved, non-sensitive context for the model."""
        lines = [f"Effective preferences for domain {self.domain}:"]
        for key, preference in sorted(self.preferences.items()):
            lines.append(f"- {key}: {preference.value!r} (source={preference.source.value})")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PreferenceCandidate:
    key: str
    value: Any
    requested_scope: PreferenceScope
    confidence: float
    evidence: str
    source_message: str
    domain: str = "customer.grocery"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_scope"] = self.requested_scope.value
        return result
