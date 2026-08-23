from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from memory_api.persistence.models import RegisteredAgentRecord


async def apply_principal_overrides(session: AsyncSession, raw_json: str) -> int:
    overrides = json.loads(raw_json or "{}")
    if not isinstance(overrides, dict):
        raise TypeError("AGENT_PRINCIPAL_OVERRIDES_JSON must be a JSON object")
    for agent_id, principal in overrides.items():
        agent = await session.get(RegisteredAgentRecord, str(agent_id))
        if agent is None:
            raise ValueError(f"principal override references unknown agent {agent_id!r}")
        agent.principal = str(principal)
    return len(overrides)
