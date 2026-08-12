from __future__ import annotations

import unittest

from app.preferences.models import PreferenceSource
from app.preferences.profile_service import MockProfilePreferenceService


class MockProfilePreferenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_adk_web_default_user_gets_demo_profile(self) -> None:
        preferences = await MockProfilePreferenceService().get_preferences(
            "user", "customer.grocery"
        )

        by_key = {preference.key: preference for preference in preferences}
        self.assertEqual(by_key["diet"].value, "vegetarian")
        self.assertIs(by_key["diet"].source, PreferenceSource.EXPLICIT_PROFILE)

    async def test_scripted_user_gets_same_demo_profile(self) -> None:
        service = MockProfilePreferenceService()
        web = await service.get_preferences("user", "customer.grocery")
        scripted = await service.get_preferences("user-123", "customer.grocery")

        self.assertEqual(
            {item.key: item.value for item in web},
            {item.key: item.value for item in scripted},
        )

    async def test_unknown_user_does_not_receive_another_users_profile(self) -> None:
        preferences = await MockProfilePreferenceService().get_preferences(
            "unknown-user", "customer.grocery"
        )

        self.assertEqual(preferences, [])


if __name__ == "__main__":
    unittest.main()
