from __future__ import annotations

import argparse
import asyncio
import os

from memory_api.persistence.readiness import DatabaseReadinessError, wait_for_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait for the Memory API database")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./shared-memory-control-plane.db"),
    )
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        successful_attempt = asyncio.run(
            wait_for_database(
                args.database_url,
                attempts=args.attempts,
                delay_seconds=args.delay_seconds,
            )
        )
    except (DatabaseReadinessError, ValueError) as error:
        print(f"Database readiness check failed: {error}")
        return 1

    print(f"Database is ready (attempt {successful_attempt}/{args.attempts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
