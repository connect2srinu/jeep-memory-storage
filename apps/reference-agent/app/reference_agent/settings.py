from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True, slots=True)
class ReferenceAgentSettings:
    memory_api_url: str = os.getenv("MEMORY_API_URL", "http://localhost:8080")
    memory_api_token: str | None = os.getenv("MEMORY_API_TOKEN")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    app_name: str = os.getenv("ADK_APP_NAME", "grocery_shared_preferences")
    agent_id: str = os.getenv("REFERENCE_AGENT_ID", "grocery-agent")
    consumer_domain: str = os.getenv("PREFERENCE_DOMAIN", "grocery")


settings = ReferenceAgentSettings()
