from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memory_api.persistence.models import (
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    ScopeDefinitionRecord,
)


async def build_vertex_context_spec(session: AsyncSession) -> dict[str, Any]:
    """Compile approved active DB schema versions into Agent Platform context_spec."""
    rows = (
        await session.execute(
            select(ProfileSchemaRecord, ProfileSchemaVersionRecord, ScopeDefinitionRecord)
            .join(
                ProfileSchemaVersionRecord,
                ProfileSchemaVersionRecord.schema_id == ProfileSchemaRecord.id,
            )
            .join(
                ScopeDefinitionRecord,
                ScopeDefinitionRecord.id == ProfileSchemaVersionRecord.scope_definition_id,
            )
            .where(
                ProfileSchemaRecord.status == "ACTIVE",
                ProfileSchemaVersionRecord.status == "ACTIVE",
                ScopeDefinitionRecord.status == "ACTIVE",
            )
            .order_by(ProfileSchemaRecord.id, ProfileSchemaVersionRecord.version)
        )
    ).all()
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for schema, version, scope in rows:
        if schema.id in seen:
            raise ValueError(f"multiple active versions found for schema {schema.id!r}")
        seen.add(schema.id)
        grouped[tuple(scope.scope_keys)].append(
            {"id": schema.id, "memory_schema": version.vertex_schema_definition}
        )
    return {
        "memory_bank_config": {
            "structured_memory_configs": [
                {
                    "scope_keys": list(scope_keys),
                    "schema_configs": sorted(configs, key=lambda item: item["id"]),
                }
                for scope_keys, configs in sorted(grouped.items())
            ]
        }
    }
