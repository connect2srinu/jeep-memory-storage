from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import Preference, PreferenceSource


class MockProfileAdapter:
    """Reference adapter for authoritative profile APIs and Memory Profile-shaped data."""

    _STANDARD_PROFILE: ClassVar[dict[str, dict[str, object]]] = {
        "customer": {
            "customer.preferred_store": "Kroger",
            "customer.diet": "vegetarian",
        },
        "grocery": {
            "grocery.preferred_brand": "Simple Truth",
            "grocery.allow_substitutions": False,
            "grocery.preferred_milk": "whole milk",
        },
    }
    _FINAL_SCENARIO_PROFILE: ClassVar[dict[str, dict[str, object]]] = {
        "customer": {"customer.preferred_store": "Store-084"},
        "grocery": {
            "grocery.preferred_product_type": "organic",
            "grocery.allow_substitutions": False,
        },
        "store": {"store.preferred_product_type": "conventional"},
        "delivery": {"delivery.preferred_window": "6PM-8PM"},
    }
    _PROFILES: ClassVar[dict[str, dict[str, dict[str, object]]]] = {
        "user": _STANDARD_PROFILE,
        "user-123": _STANDARD_PROFILE,
        "U123": _FINAL_SCENARIO_PROFILE,
    }

    def __init__(self, catalog: PreferenceCatalog) -> None:
        self.catalog = catalog

    async def get_preferences(
        self, user_id: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        now = datetime.now(UTC)
        profile = self._PROFILES.get(user_id, {})
        result: list[Preference] = []
        for domain in domains:
            for key, value in profile.get(domain, {}).items():
                entry = self.catalog.lookup(key, domain)
                result.append(
                    Preference(
                        key=key,
                        value=value,
                        source=PreferenceSource.EXPLICIT_PROFILE,
                        owner_domain=domain,
                        confidence=1.0,
                        updated_at=now,
                        confirmed=True,
                        canonical=bool(entry),
                        schema_version=entry.schema_version if entry else "1",
                        sensitivity=entry.sensitivity if entry else "normal",
                        provenance={
                            "service": "mock-profile-api",
                            "record_id": f"{user_id}:{key}",
                        },
                    )
                )
        return result
