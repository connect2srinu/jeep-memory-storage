from __future__ import annotations

import unittest

from app.shared_memory.adapters import InMemoryLongTermMemoryAdapter
from app.shared_memory.models import PreferenceSource
from tests.test_shared_memory_platform import (
    FailingDynamicMemoryAdapter,
    StaticProfileAdapter,
    build_platform,
    preference,
)


class ContextServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_context_normalizes_and_resolves_all_sources(self) -> None:
        profile = StaticProfileAdapter(
            [
                preference(
                    "grocery.preferred_brand",
                    "Simple Truth",
                    PreferenceSource.EXPLICIT_PROFILE,
                    "grocery",
                )
            ]
        )
        memory = InMemoryLongTermMemoryAdapter(
            [
                (
                    "U123",
                    "shared-memory-test",
                    preference(
                        "grocery.organic_preference",
                        True,
                        PreferenceSource.DOMAIN_MEMORY,
                        "grocery",
                    ),
                )
            ]
        )
        platform, session, _, _ = build_platform(
            profile_adapter=profile, dynamic_backend=memory
        )
        await session.save_session_preference(
            "U123",
            "S456",
            preference(
                "grocery.allow_substitutions",
                True,
                PreferenceSource.SESSION_OVERRIDE,
                "grocery",
            ),
        )
        context = await platform.get_effective_context(
            user_id="U123",
            session_id="S456",
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertEqual(
            context.preferences["preferred_brand"].preference.source,
            PreferenceSource.EXPLICIT_PROFILE,
        )
        self.assertEqual(
            context.preferences["organic_preference"].preference.source,
            PreferenceSource.DOMAIN_MEMORY,
        )
        self.assertEqual(
            context.preferences["allow_substitutions"].preference.source,
            PreferenceSource.SESSION_OVERRIDE,
        )

    async def test_memory_failure_degrades_safely(self) -> None:
        profile = StaticProfileAdapter(
            [
                preference(
                    "grocery.preferred_brand",
                    "Simple Truth",
                    PreferenceSource.EXPLICIT_PROFILE,
                    "grocery",
                )
            ]
        )
        platform, _, _, _ = build_platform(
            profile_adapter=profile, dynamic_backend=FailingDynamicMemoryAdapter()
        )
        context = await platform.get_effective_context(
            user_id="U123",
            session_id="S456",
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertIn("preferred_brand", context.preferences)
        self.assertIn("dynamic_memory unavailable", context.warnings)


if __name__ == "__main__":
    unittest.main()
