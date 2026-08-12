from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    project: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    use_vertex_ai: bool = _bool("GOOGLE_GENAI_USE_VERTEXAI", True)
    use_enterprise: bool = _bool("GOOGLE_GENAI_USE_ENTERPRISE", True)
    agent_engine_id: str | None = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    sessions_id: str | None = os.getenv("AGENT_PLATFORM_SESSIONS_ID")
    memory_bank_id: str | None = os.getenv("AGENT_PLATFORM_MEMORY_BANK_ID")
    staging_bucket: str | None = os.getenv("AGENT_PLATFORM_STAGING_BUCKET")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    app_name: str = os.getenv("ADK_APP_NAME", "grocery_shared_preferences")
    domain: str = os.getenv("PREFERENCE_DOMAIN", "customer.grocery")
    minimum_memory_confidence: float = float(os.getenv("MINIMUM_MEMORY_CONFIDENCE", "0.70"))

    @property
    def session_resource_id(self) -> str | None:
        return self.sessions_id or self.agent_engine_id

    @property
    def memory_resource_id(self) -> str | None:
        return self.memory_bank_id or self.agent_engine_id

    @property
    def cloud_state_configured(self) -> bool:
        return bool(self.project and self.session_resource_id and self.memory_resource_id)


settings = Settings()
