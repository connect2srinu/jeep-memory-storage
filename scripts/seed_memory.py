from __future__ import annotations

import argparse
import asyncio

from app.shared_memory.adapters import InMemorySessionAdapter
from app.shared_memory.bootstrap import platform_dependencies
from app.shared_memory.models import PreferenceCandidate, PreferenceScope


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit a validated long-term preference to Agent Platform Memory Bank."
    )
    parser.add_argument("--user-id", default="user-123")
    parser.add_argument("--session-id", default="seed-session")
    parser.add_argument("--consumer-domain", default="grocery")
    parser.add_argument("--domain", default="grocery")
    parser.add_argument("--key", default="organic")
    parser.add_argument("--value", default="true")
    args = parser.parse_args()
    value = {"true": True, "false": False}.get(args.value.lower(), args.value)
    platform = platform_dependencies.build_service(InMemorySessionAdapter())
    candidate = PreferenceCandidate(
        key=args.key,
        value=value,
        proposed_domain=args.domain,
        requested_scope=PreferenceScope.LONG_TERM,
        confidence=0.93,
        source="SEED_SCRIPT",
        source_message=f"seed {args.key}",
        user_id=args.user_id,
        session_id=args.session_id,
        explicit=True,
        evidence="intentional POC seed",
    )
    result = await platform.submit_preference(
        candidate=candidate,
        consumer_domain=args.consumer_domain,
        agent_id=f"{args.consumer_domain}-agent",
    )
    print(result.to_dict())


if __name__ == "__main__":
    asyncio.run(main())
