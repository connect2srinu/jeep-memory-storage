from __future__ import annotations

import os
from dataclasses import dataclass

from memory_api.security.authentication import (
    AgentAuthenticator,
    GoogleIdTokenAuthenticator,
    LocalAgentAuthenticator,
)


def environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class MemoryApiSettings:
    database_url: str
    auth_enabled: bool
    google_id_token_audience: str | None
    include_legacy_routes: bool = False

    @classmethod
    def from_environment(cls) -> MemoryApiSettings:
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", "sqlite+aiosqlite:///./shared-memory-control-plane.db"
            ),
            auth_enabled=environment_bool("AUTH_ENABLED", False),
            google_id_token_audience=os.getenv("GOOGLE_ID_TOKEN_AUDIENCE"),
            include_legacy_routes=environment_bool("INCLUDE_LEGACY_ROUTES", False),
        )

    def authenticator(self) -> AgentAuthenticator:
        if not self.auth_enabled:
            return LocalAgentAuthenticator()
        return GoogleIdTokenAuthenticator(self.google_id_token_audience or "")
