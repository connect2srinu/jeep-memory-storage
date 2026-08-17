from __future__ import annotations

import argparse
import asyncio

from google.adk import Runner
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent
from app.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Grocery reference-agent turn.")
    parser.add_argument("message")
    parser.add_argument("--user-id", default="user-123")
    parser.add_argument("--session-id", default="session-456")
    args = parser.parse_args()

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=settings.app_name,
        user_id=args.user_id,
        session_id=args.session_id,
    )
    runner = Runner(
        agent=root_agent,
        app_name=settings.app_name,
        session_service=session_service,
        memory_service=InMemoryMemoryService(),
    )
    content = types.Content(role="user", parts=[types.Part.from_text(text=args.message)])
    async for event in runner.run_async(
        user_id=args.user_id, session_id=session.id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            print(event.content.parts[0].text)


if __name__ == "__main__":
    asyncio.run(main())
