from __future__ import annotations

import argparse
import asyncio
import json

from app.shared_memory.bootstrap import platform_dependencies


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect normalized domain-scoped memory.")
    parser.add_argument("--user-id", default="user-123")
    parser.add_argument("--domains", default="grocery")
    args = parser.parse_args()
    domains = tuple(value.strip() for value in args.domains.split(",") if value.strip())
    dynamic = await platform_dependencies.long_term_service.get_dynamic_preferences(
        args.user_id, platform_dependencies.app_name, domains
    )
    profiles = await platform_dependencies.long_term_service.get_memory_profile_preferences(
        args.user_id, platform_dependencies.app_name, domains
    )
    print(
        json.dumps(
            {
                "dynamic_memories": [item.public_dict() for item in dynamic],
                "memory_profiles": [item.public_dict() for item in profiles],
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
