from __future__ import annotations

import asyncio
import unittest

from app.preferences.memory_service import LongTermPreferenceService
from app.preferences.models import Preference, PreferenceCandidate, PreferenceSource
from app.preferences.profile_service import ProfilePreferenceService
from app.preferences.resolver import PreferenceResolver
from app.services.preference_context_service import PreferenceContextService

DOMAIN = "customer.grocery"


class StubProfile(ProfilePreferenceService):
    async def get_preferences(self, user_id: str, domain: str) -> list[Preference]:
        await asyncio.sleep(0.01)
        return [
            Preference(
                "preferred_brand", "Simple Truth", PreferenceSource.EXPLICIT_PROFILE, domain=domain
            )
        ]


class StubMemory(LongTermPreferenceService):
    async def retrieve_preferences(
        self, user_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        await asyncio.sleep(0.01)
        return [
            Preference(
                "organic", True, PreferenceSource.LONG_TERM_MEMORY, domain=domain, confidence=0.93
            )
        ]

    async def promote_candidate(
        self, user_id: str, agent_id: str, candidate: PreferenceCandidate
    ) -> str:
        return "memories/1"


class FailingMemory(StubMemory):
    async def retrieve_preferences(
        self, user_id: str, agent_id: str, domain: str
    ) -> list[Preference]:
        raise ConnectionError("simulated outage")


class ContextServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_context_normalizes_and_resolves_all_sources(self) -> None:
        service = PreferenceContextService(
            profile_service=StubProfile(),
            memory_service=StubMemory(),
            session_store=None,
            resolver=PreferenceResolver(0.7),
            defaults=[
                Preference("allow_substitutions", False, PreferenceSource.DEFAULT, domain=DOMAIN)
            ],
        )
        state = {
            "preferences:customer.grocery": {
                "allow_substitutions": {"value": True, "updated_at": "2026-01-01T00:00:00+00:00"}
            }
        }
        context = await service.build_context(
            "user-123", "session-456", "grocery", DOMAIN, session_state=state
        )
        self.assertEqual(
            context.preferences["preferred_brand"].source, PreferenceSource.EXPLICIT_PROFILE
        )
        self.assertEqual(context.preferences["organic"].source, PreferenceSource.LONG_TERM_MEMORY)
        self.assertEqual(
            context.preferences["allow_substitutions"].source, PreferenceSource.SESSION_OVERRIDE
        )

    async def test_memory_failure_degrades_safely(self) -> None:
        service = PreferenceContextService(
            profile_service=StubProfile(),
            memory_service=FailingMemory(),
            session_store=None,
            resolver=PreferenceResolver(),
        )
        context = await service.build_context(
            "user-123", "session-456", "grocery", DOMAIN, session_state={}
        )
        self.assertIn("preferred_brand", context.preferences)
        self.assertIn("long_term_memory unavailable", context.warnings)


if __name__ == "__main__":
    unittest.main()
