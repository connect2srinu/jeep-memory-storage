from __future__ import annotations

from dataclasses import asdict, dataclass, field
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


class PreferenceScope(StrEnum):
    SESSION = "SESSION"
    LONG_TERM = "LONG_TERM"


class CandidateDisposition(StrEnum):
    STORED_IN_SESSION = "STORED_IN_SESSION"
    STORED_IN_DYNAMIC_MEMORY = "STORED_IN_DYNAMIC_MEMORY"
    CANONICAL_PROFILE_CANDIDATE = "CANONICAL_PROFILE_CANDIDATE"
    CROSS_DOMAIN_CANDIDATE = "CROSS_DOMAIN_CANDIDATE"
    REJECTED = "REJECTED"
    NOT_PERSISTED = "NOT_PERSISTED"


@dataclass(frozen=True, slots=True)
class Preference:
    """Framework-neutral normalized preference used by the platform."""

    key: str
    value: Any
    source: PreferenceSource
    owner_domain: str
    scope: PreferenceScope = PreferenceScope.LONG_TERM
    confidence: float | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None
    confirmed: bool = True
    canonical: bool = False
    schema_version: str = "1"
    sensitivity: str = "normal"
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.owner_domain.strip():
            raise ValueError("preference key and owner_domain must be non-empty")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        for timestamp in (self.updated_at, self.expires_at):
            if timestamp is not None and timestamp.tzinfo is None:
                raise ValueError("timestamps must be timezone-aware")

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or datetime.now(UTC))

    def public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source"] = self.source.value
        payload["scope"] = self.scope.value
        for name in ("updated_at", "expires_at"):
            payload[name] = payload[name].isoformat() if payload[name] else None
        return payload


@dataclass(frozen=True, slots=True)
class PreferenceCandidate:
    key: str
    value: Any
    proposed_domain: str
    requested_scope: PreferenceScope
    confidence: float
    source: str
    source_message: str
    user_id: str
    session_id: str
    explicit: bool = True
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.proposed_domain.strip():
            raise ValueError("candidate key and proposed_domain must be non-empty")
        if not 0 <= self.confidence <= 1:
            raise ValueError("candidate confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requested_scope"] = self.requested_scope.value
        return payload


@dataclass(frozen=True, slots=True)
class ResolvedPreference:
    preference: Preference
    resolution_reason: str
    policy_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.preference.public_dict()
        payload["resolution_reason"] = self.resolution_reason
        payload["policy_id"] = self.policy_id
        return payload


@dataclass(frozen=True, slots=True)
class EffectivePreferenceContext:
    user_id: str
    session_id: str
    consumer_domain: str
    agent_id: str
    preferences: dict[str, ResolvedPreference]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    warnings: tuple[str, ...] = ()
    readable_domains: tuple[str, ...] = ()
    snapshot_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "consumer_domain": self.consumer_domain,
            "agent_id": self.agent_id,
            "preferences": {
                key: value.to_dict() for key, value in sorted(self.preferences.items())
            },
            "generated_at": self.generated_at.isoformat(),
            "warnings": list(self.warnings),
            "readable_domains": list(self.readable_domains),
            "snapshot_version": self.snapshot_version,
        }

    def for_prompt(self) -> str:
        lines = [f"Effective preferences for consumer domain {self.consumer_domain}:"]
        for key, resolved in sorted(self.preferences.items()):
            preference = resolved.preference
            lines.append(
                f"- {key}: {preference.value!r} "
                f"(source={preference.source.value}, owner={preference.owner_domain}, "
                f"reason={resolved.resolution_reason})"
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    disposition: CandidateDisposition
    candidate: PreferenceCandidate
    canonical_key: str
    owner_domain: str
    message: str
    reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.disposition.value,
            "candidate": self.candidate.to_dict(),
            "canonical_key": self.canonical_key,
            "owner_domain": self.owner_domain,
            "message": self.message,
            "reference": self.reference,
        }

