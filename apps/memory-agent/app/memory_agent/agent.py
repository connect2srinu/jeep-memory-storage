"""ADK agent with split memory: short-term in Postgres, long-term in Memory Bank.

Short-term (session/conversation) state is persisted by ADK's ``DatabaseSessionService``
into Cloud SQL / PostgreSQL. Long-term memory is stored in and recalled from Vertex AI
Memory Bank via ``VertexAiMemoryBankService``. The ``Runner`` composes the two independently.
"""

from __future__ import annotations

from google.adk import Runner
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.sessions import DatabaseSessionService
from google.adk.tools.load_memory_tool import LoadMemoryTool
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from .settings import settings

INSTRUCTION = """
You are a helpful assistant with two kinds of memory.

Short-term memory is the current conversation (this session). Long-term memory holds durable
facts the user has shared in earlier sessions, retrieved from Memory Bank. Relevant long-term
memories are preloaded into your context at the start of a session; call the load_memory tool
when you need to search for something specific that was not preloaded.

Use long-term memories to personalize your answers. Never invent facts the user did not state.
"""


async def persist_long_term_memory(callback_context: CallbackContext) -> None:
    """After each turn, write the completed session to Memory Bank (long-term memory)."""
    await callback_context.add_session_to_memory()


root_agent = Agent(
    name="dual_memory_agent",
    model=Gemini(model=settings.model),
    instruction=INSTRUCTION,
    tools=[PreloadMemoryTool(), LoadMemoryTool()],
    after_agent_callback=persist_long_term_memory,
)

# Exposed for `adk web` / `adk api_server` discovery.
app = App(name=settings.app_name, root_agent=root_agent)


def build_session_service() -> DatabaseSessionService:
    """Short-term memory: ADK sessions persisted in Cloud SQL / PostgreSQL."""
    return DatabaseSessionService(db_url=settings.sessions_database_url)


def build_memory_service() -> VertexAiMemoryBankService:
    """Long-term memory: Vertex AI Memory Bank."""
    if not settings.project or not settings.agent_engine_id:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT and AGENT_PLATFORM_MEMORY_BANK_ID are required for Memory Bank"
        )
    return VertexAiMemoryBankService(
        project=settings.project,
        location=settings.location,
        agent_engine_id=settings.agent_engine_id,
    )


def build_runner() -> Runner:
    """Compose the agent with short-term (Postgres) and long-term (Memory Bank) memory."""
    return Runner(
        agent=root_agent,
        app_name=settings.app_name,
        session_service=build_session_service(),
        memory_service=build_memory_service(),
    )
