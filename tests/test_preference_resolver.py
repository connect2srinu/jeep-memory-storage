from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.preferences.models import Preference, PreferenceSource
from app.preferences.resolver import PreferenceResolver

DOMAIN = "customer.grocery"


def pref(key: str, value: object, source: PreferenceSource, **kwargs: object) -> Preference:
    return Preference(key, value, source, domain=DOMAIN, **kwargs)


class PreferenceResolverTests(unittest.TestCase):
    def resolve(self, *, threshold: float = 0.0, **sources: object):
        return PreferenceResolver(threshold).resolve(
            user_id="user-123",
            session_id="session-456",
            agent_id="grocery",
            domain=DOMAIN,
            **sources,
        )

    def test_session_overrides_explicit_profile(self) -> None:
        context = self.resolve(
            session_preferences=[
                pref("allow_substitutions", True, PreferenceSource.SESSION_OVERRIDE)
            ],
            explicit_profile_preferences=[
                pref("allow_substitutions", False, PreferenceSource.EXPLICIT_PROFILE)
            ],
        )
        self.assertTrue(context.preferences["allow_substitutions"].value)
        self.assertIs(
            context.preferences["allow_substitutions"].source, PreferenceSource.SESSION_OVERRIDE
        )

    def test_explicit_profile_overrides_long_term(self) -> None:
        context = self.resolve(
            explicit_profile_preferences=[
                pref("preferred_milk", "whole milk", PreferenceSource.EXPLICIT_PROFILE)
            ],
            long_term_preferences=[
                pref("preferred_milk", "oat milk", PreferenceSource.LONG_TERM_MEMORY)
            ],
        )
        self.assertEqual(context.preferences["preferred_milk"].value, "whole milk")

    def test_long_term_overrides_default(self) -> None:
        context = self.resolve(
            long_term_preferences=[pref("organic", True, PreferenceSource.LONG_TERM_MEMORY)],
            defaults=[pref("organic", False, PreferenceSource.DEFAULT)],
        )
        self.assertTrue(context.preferences["organic"].value)

    def test_session_only_applies_when_present(self) -> None:
        context = self.resolve(
            session_preferences=[],
            explicit_profile_preferences=[
                pref("diet", "vegetarian", PreferenceSource.EXPLICIT_PROFILE)
            ],
        )
        self.assertEqual(context.preferences["diet"].source, PreferenceSource.EXPLICIT_PROFILE)

    def test_unrelated_preferences_merge(self) -> None:
        context = self.resolve(
            session_preferences=[pref("budget", 100, PreferenceSource.SESSION_OVERRIDE)],
            explicit_profile_preferences=[
                pref("diet", "vegetarian", PreferenceSource.EXPLICIT_PROFILE)
            ],
            long_term_preferences=[pref("organic", True, PreferenceSource.LONG_TERM_MEMORY)],
            defaults=[pref("allow_substitutions", False, PreferenceSource.DEFAULT)],
        )
        self.assertEqual(
            set(context.preferences), {"budget", "diet", "organic", "allow_substitutions"}
        )

    def test_expired_preferences_are_ignored(self) -> None:
        expired = datetime.now(UTC) - timedelta(seconds=1)
        context = self.resolve(
            session_preferences=[
                pref("diet", "vegan", PreferenceSource.SESSION_OVERRIDE, expires_at=expired)
            ],
            explicit_profile_preferences=[
                pref("diet", "vegetarian", PreferenceSource.EXPLICIT_PROFILE)
            ],
        )
        self.assertEqual(context.preferences["diet"].value, "vegetarian")

    def test_low_confidence_memory_is_optionally_filtered(self) -> None:
        context = self.resolve(
            threshold=0.8,
            long_term_preferences=[
                pref("organic", True, PreferenceSource.LONG_TERM_MEMORY, confidence=0.5)
            ],
            defaults=[pref("organic", False, PreferenceSource.DEFAULT)],
        )
        self.assertFalse(context.preferences["organic"].value)

    def test_provenance_survives_resolution(self) -> None:
        provenance = {"service": "memory-bank", "memory_name": "memories/42"}
        context = self.resolve(
            long_term_preferences=[
                pref("organic", True, PreferenceSource.LONG_TERM_MEMORY, provenance=provenance)
            ]
        )
        self.assertEqual(context.preferences["organic"].provenance, provenance)

    def test_other_domain_is_never_used(self) -> None:
        pharmacy = Preference(
            "diet", "anything", PreferenceSource.SESSION_OVERRIDE, domain="customer.pharmacy"
        )
        context = self.resolve(session_preferences=[pharmacy])
        self.assertNotIn("diet", context.preferences)


if __name__ == "__main__":
    unittest.main()
