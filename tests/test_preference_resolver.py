from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import Preference, PreferenceScope, PreferenceSource
from app.shared_memory.policies import PreferencePolicyRegistry
from app.shared_memory.resolver import PreferenceResolver


def pref(
    key: str,
    value: object,
    source: PreferenceSource,
    domain: str = "grocery",
    **kwargs: object,
) -> Preference:
    return Preference(
        key=key,
        value=value,
        source=source,
        owner_domain=domain,
        scope=(
            PreferenceScope.SESSION
            if source is PreferenceSource.SESSION_OVERRIDE
            else PreferenceScope.LONG_TERM
        ),
        updated_at=datetime.now(UTC),
        **kwargs,
    )


class PreferenceResolverTests(unittest.TestCase):
    def resolve(self, values: list[Preference], threshold: float = 0.0):
        catalog = PreferenceCatalog.default()
        policies = PreferencePolicyRegistry.default(threshold)
        return PreferenceResolver(catalog, policies).resolve(
            user_id="U123",
            session_id="S456",
            consumer_domain="grocery",
            agent_id="grocery-agent",
            preferences=values,
            readable_domains=policies.domain_policy("grocery").read,
        )

    def test_session_overrides_explicit_profile(self) -> None:
        context = self.resolve(
            [
                pref("grocery.allow_substitutions", False, PreferenceSource.EXPLICIT_PROFILE),
                pref("grocery.allow_substitutions", True, PreferenceSource.SESSION_OVERRIDE),
            ]
        )
        self.assertTrue(context.preferences["allow_substitutions"].preference.value)

    def test_explicit_profile_overrides_long_term(self) -> None:
        context = self.resolve(
            [
                pref("grocery.preferred_milk", "oat", PreferenceSource.DYNAMIC_MEMORY),
                pref("grocery.preferred_milk", "whole", PreferenceSource.EXPLICIT_PROFILE),
            ]
        )
        self.assertEqual(context.preferences["preferred_milk"].preference.value, "whole")

    def test_long_term_overrides_default(self) -> None:
        context = self.resolve(
            [
                pref("grocery.organic_preference", False, PreferenceSource.DEFAULT),
                pref("grocery.organic_preference", True, PreferenceSource.DOMAIN_MEMORY),
            ]
        )
        self.assertTrue(context.preferences["organic_preference"].preference.value)

    def test_unrelated_preferences_merge(self) -> None:
        context = self.resolve(
            [
                pref("grocery.budget", 100, PreferenceSource.SESSION_OVERRIDE),
                pref("customer.diet", "vegetarian", PreferenceSource.EXPLICIT_PROFILE, "customer"),
                pref("grocery.organic_preference", True, PreferenceSource.DOMAIN_MEMORY),
            ]
        )
        self.assertEqual(set(context.preferences), {"budget", "diet", "organic_preference"})

    def test_expired_preferences_are_ignored(self) -> None:
        context = self.resolve(
            [
                pref(
                    "grocery.diet_override",
                    "none",
                    PreferenceSource.SESSION_OVERRIDE,
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),
                ),
                pref("customer.diet", "vegetarian", PreferenceSource.EXPLICIT_PROFILE, "customer"),
            ]
        )
        self.assertNotIn("diet_override", context.preferences)
        self.assertEqual(context.preferences["diet"].preference.value, "vegetarian")

    def test_low_confidence_memory_is_filtered(self) -> None:
        context = self.resolve(
            [pref("grocery.banana_ripeness", "green", PreferenceSource.DYNAMIC_MEMORY, confidence=0.5)],
            threshold=0.8,
        )
        self.assertNotIn("banana_ripeness", context.preferences)

    def test_provenance_survives_resolution(self) -> None:
        provenance = {"service": "memory-bank", "memory_name": "memories/42"}
        context = self.resolve(
            [pref("grocery.banana_ripeness", "green", PreferenceSource.DYNAMIC_MEMORY, provenance=provenance)]
        )
        self.assertEqual(
            context.preferences["banana_ripeness"].preference.provenance, provenance
        )

    def test_pharmacy_domain_is_never_used_by_grocery(self) -> None:
        context = self.resolve(
            [pref("pharmacy.medication", "anything", PreferenceSource.SESSION_OVERRIDE, "pharmacy")]
        )
        self.assertNotIn("medication", context.preferences)


if __name__ == "__main__":
    unittest.main()
