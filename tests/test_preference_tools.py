from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.preferences.memory_service import (
    LongTermPreferenceService,
    MemoryBankNotConfiguredError,
)
from app.preferences.models import PreferenceCandidate
from app.tools import preference_tools
from app.tools.preference_tools import ToolRuntime, _identity


class UnconfiguredMemoryService(LongTermPreferenceService):
    async def retrieve_preferences(self, user_id: str, agent_id: str, domain: str):
        raise MemoryBankNotConfiguredError("Memory Bank is not configured")

    async def promote_candidate(
        self, user_id: str, agent_id: str, candidate: PreferenceCandidate
    ) -> str:
        raise MemoryBankNotConfiguredError("Memory Bank is not configured")


class PreferenceToolIdentityTests(unittest.TestCase):
    def test_uses_adk_native_identity_for_web_sessions(self) -> None:
        context = SimpleNamespace(
            user_id="web-user",
            session=SimpleNamespace(id="web-session", user_id="web-user"),
            state={},
        )

        self.assertEqual(_identity(context), ("web-user", "web-session"))

    def test_falls_back_to_initialized_state_for_legacy_context(self) -> None:
        context = SimpleNamespace(
            state={
                "preference_user_id": "legacy-user",
                "preference_session_id": "legacy-session",
            }
        )

        self.assertEqual(_identity(context), ("legacy-user", "legacy-session"))

    def test_native_identity_wins_over_stale_state(self) -> None:
        context = SimpleNamespace(
            user_id="native-user",
            session=SimpleNamespace(id="native-session", user_id="native-user"),
            state={
                "preference_user_id": "stale-user",
                "preference_session_id": "stale-session",
            },
        )

        self.assertEqual(_identity(context), ("native-user", "native-session"))


class PreferencePromotionTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_memory_returns_controlled_result(self) -> None:
        previous_runtime = preference_tools._runtime
        preference_tools.configure_runtime(
            ToolRuntime(
                context_service=SimpleNamespace(),
                memory_service=UnconfiguredMemoryService(),
                agent_id="grocery_shared_preferences",
                domain="customer.grocery",
            )
        )
        context = SimpleNamespace(
            user_id="user",
            session=SimpleNamespace(id="session-1", user_id="user"),
            state={},
        )
        try:
            result = await preference_tools.process_preference_statement(
                "I always prefer organic produce.", context
            )
        finally:
            preference_tools._runtime = previous_runtime

        self.assertEqual(result["status"], "not_persisted")
        self.assertEqual(result["reason"], "memory_bank_not_configured")
        self.assertFalse(result["memory_bank_written"])


if __name__ == "__main__":
    unittest.main()
