from __future__ import annotations

import os
import unittest

from app.preferences.memory_service import VertexAiMemoryBankPreferenceService


@unittest.skipUnless(
    os.getenv("RUN_GCP_INTEGRATION_TESTS") == "1", "requires configured GCP project"
)
class AgentPlatformIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_memory_bank_retrieval(self) -> None:
        service = VertexAiMemoryBankPreferenceService(
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            agent_engine_id=os.environ["AGENT_PLATFORM_MEMORY_BANK_ID"],
        )
        preferences = await service.retrieve_preferences(
            "user-123", os.getenv("ADK_APP_NAME", "grocery_shared_preferences"), "customer.grocery"
        )
        self.assertIsInstance(preferences, list)
