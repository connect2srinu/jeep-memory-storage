from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from .models import EffectivePreferenceContext, Preference, PreferenceSource


class PreferenceResolver:
    """Pure, framework-independent preference precedence logic."""

    _ORDER = (
        PreferenceSource.DEFAULT,
        PreferenceSource.LONG_TERM_MEMORY,
        PreferenceSource.EXPLICIT_PROFILE,
        PreferenceSource.SESSION_OVERRIDE,
    )

    def __init__(self, minimum_memory_confidence: float = 0.0) -> None:
        if not 0 <= minimum_memory_confidence <= 1:
            raise ValueError("minimum_memory_confidence must be between 0 and 1")
        self.minimum_memory_confidence = minimum_memory_confidence

    def resolve(
        self,
        *,
        user_id: str,
        session_id: str,
        agent_id: str,
        domain: str,
        session_preferences: Iterable[Preference] = (),
        explicit_profile_preferences: Iterable[Preference] = (),
        long_term_preferences: Iterable[Preference] = (),
        defaults: Iterable[Preference] = (),
        now: datetime | None = None,
        warnings: tuple[str, ...] = (),
    ) -> EffectivePreferenceContext:
        current = now or datetime.now(UTC)
        by_source = {
            PreferenceSource.DEFAULT: defaults,
            PreferenceSource.LONG_TERM_MEMORY: long_term_preferences,
            PreferenceSource.EXPLICIT_PROFILE: explicit_profile_preferences,
            PreferenceSource.SESSION_OVERRIDE: session_preferences,
        }
        resolved: dict[str, Preference] = {}
        for source in self._ORDER:
            for preference in by_source[source]:
                if preference.source is not source:
                    raise ValueError(f"{preference.key}: source does not match input collection")
                if preference.domain != domain or preference.is_expired(current):
                    continue
                if (
                    source is PreferenceSource.LONG_TERM_MEMORY
                    and preference.confidence is not None
                    and preference.confidence < self.minimum_memory_confidence
                ):
                    continue
                existing = resolved.get(preference.key)
                if (
                    existing is None
                    or self._is_newer(preference, existing)
                    or source is not existing.source
                ):
                    resolved[preference.key] = preference
        return EffectivePreferenceContext(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            domain=domain,
            preferences=resolved,
            warnings=warnings,
        )

    @staticmethod
    def _is_newer(candidate: Preference, existing: Preference) -> bool:
        if candidate.updated_at is None:
            return existing.updated_at is None
        return existing.updated_at is None or candidate.updated_at >= existing.updated_at
