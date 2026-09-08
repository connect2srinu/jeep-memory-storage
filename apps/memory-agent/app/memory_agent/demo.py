"""End-to-end demo of the split memory model.

Session 1 stores short-term state in Postgres and, via the after-agent callback, writes the
session into Memory Bank (long-term). Session 2 is a fresh conversation whose short-term state
is empty, yet the agent recalls the earlier fact from Memory Bank.

Run (needs Application Default Credentials, a Memory Bank Agent Engine, and Postgres):

    GOOGLE_CLOUD_PROJECT=... AGENT_PLATFORM_MEMORY_BANK_ID=... \
    SESSIONS_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \
    python -m memory_agent.demo
"""

from __future__ import annotations

import asyncio

from google.genai import types

from .agent import build_runner
from .settings import settings


async def _say(runner, user_id: str, session_id: str, text: str) -> None:
    print(f"\n[{session_id[:8]}] user: {text}")
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"[{session_id[:8]}] agent: {part.text.strip()}")


async def main() -> None:
    runner = build_runner()
    user_id = "demo-user"

    # Session 1 — short-term state persists to Postgres; the callback writes it to Memory Bank.
    first = await runner.session_service.create_session(app_name=settings.app_name, user_id=user_id)
    await _say(runner, user_id, first.id, "I always prefer a window seat when I fly.")

    # Session 2 — a fresh session (empty short-term state) recalls the fact from long-term memory.
    second = await runner.session_service.create_session(app_name=settings.app_name, user_id=user_id)
    await _say(runner, user_id, second.id, "Which seat do I prefer on flights?")


if __name__ == "__main__":
    asyncio.run(main())
