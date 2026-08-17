from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.shared_memory.adapters import MemoryBankNotConfiguredError
from app.shared_memory.bootstrap import platform_dependencies
from app.tools import preference_tools
from app.tools.preference_tools import _identity


class UnconfiguredMemoryBackend:
    async def get_dynamic_preferences(self, user_id: str, app_name: str, domains: tuple[str, ...]):
        raise MemoryBankNotConfiguredError("Memory Bank is not configured")

    async def store_dynamic_preference(self, user_id: str, app_name: str, preference: object) -> str:
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
        previous_backend = platform_dependencies.long_term_service.dynamic_backend
        platform_dependencies.long_term_service.dynamic_backend = UnconfiguredMemoryBackend()
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
            platform_dependencies.long_term_service.dynamic_backend = previous_backend

        self.assertEqual(result["status"], "NOT_PERSISTED")
        self.assertIn("not persisted", result["message"])


if __name__ == "__main__":
    unittest.main()
