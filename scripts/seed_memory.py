from __future__ import annotations

import argparse
import asyncio

from app.config import settings
from app.preferences.memory_service import VertexAiMemoryBankPreferenceService
from app.preferences.models import PreferenceCandidate, PreferenceScope


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a real Agent Platform Memory Bank preference."
    )
    parser.add_argument("--user-id", default="user-123")
    parser.add_argument("--key", default="organic")
    parser.add_argument("--value", default="true")
    args = parser.parse_args()
    if not settings.project or not settings.memory_resource_id:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT and AGENT_PLATFORM_MEMORY_BANK_ID")
    value = {"true": True, "false": False}.get(args.value.lower(), args.value)
    service = VertexAiMemoryBankPreferenceService(
        project=settings.project,
        location=settings.location,
        agent_engine_id=settings.memory_resource_id,
    )
    candidate = PreferenceCandidate(
        key=args.key,
        value=value,
        requested_scope=PreferenceScope.USER,
        confidence=0.93,
        evidence="POC seed script",
        source_message=f"seed {args.key}",
        domain=settings.domain,
    )
    print(await service.promote_candidate(args.user_id, settings.app_name, candidate))


if __name__ == "__main__":
    asyncio.run(main())
