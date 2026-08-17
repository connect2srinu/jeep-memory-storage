from __future__ import annotations

from dataclasses import dataclass

from app.shared_memory.models import EffectivePreferenceContext
from app.shared_memory.services import SharedMemoryPlatformService


@dataclass(frozen=True, slots=True)
class ReferenceConsumer:
    domain: str
    agent_id: str
    platform: SharedMemoryPlatformService

    async def get_context(self, user_id: str, session_id: str) -> EffectivePreferenceContext:
        return await self.platform.get_effective_context(
            user_id=user_id,
            session_id=session_id,
            consumer_domain=self.domain,
            agent_id=self.agent_id,
        )


def store_consumer(platform: SharedMemoryPlatformService) -> ReferenceConsumer:
    return ReferenceConsumer("store", "store-agent", platform)


def delivery_consumer(platform: SharedMemoryPlatformService) -> ReferenceConsumer:
    return ReferenceConsumer("delivery", "delivery-agent", platform)

