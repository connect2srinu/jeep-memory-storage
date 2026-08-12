from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import ClassVar

from .models import Preference, PreferenceSource


class ProfilePreferenceService(ABC):
    @abstractmethod
    async def get_preferences(self, user_id: str, domain: str) -> list[Preference]:
        """Return explicit preferences for exactly one user and domain."""


class MockProfilePreferenceService(ProfilePreferenceService):
    _GROCERY_DEMO_PROFILE: ClassVar[dict[str, object]] = {
        "diet": "vegetarian",
        "preferred_brand": "Simple Truth",
        "allow_substitutions": False,
        "preferred_store": "Kroger",
        "preferred_milk": "whole milk",
    }
    _PROFILES: ClassVar[dict[str, dict[str, dict[str, object]]]] = {
        # ADK Web uses "user" unless the UI URL supplies ?userId=... . Both
        # identities intentionally point at the same POC profile so the
        # precedence demo works out of the box and with the scripted user.
        "user": {"customer.grocery": _GROCERY_DEMO_PROFILE},
        "user-123": {"customer.grocery": _GROCERY_DEMO_PROFILE},
    }

    async def get_preferences(self, user_id: str, domain: str) -> list[Preference]:
        now = datetime.now(UTC)
        values = self._PROFILES.get(user_id, {}).get(domain, {})
        return [
            Preference(
                key=key,
                value=value,
                source=PreferenceSource.EXPLICIT_PROFILE,
                domain=domain,
                confidence=1.0,
                updated_at=now,
                provenance={"service": "mock-profile-api", "record_id": f"{user_id}:{key}"},
            )
            for key, value in values.items()
        ]
