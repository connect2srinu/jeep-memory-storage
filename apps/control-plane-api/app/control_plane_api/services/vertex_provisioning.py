from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.persistence.models import (
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    ScopeDefinitionRecord,
)


async def build_vertex_context_spec(
    session: AsyncSession, *, generation_model: str | None = None
) -> dict[str, Any]:
    """Compile approved active DB schema versions into Agent Platform context_spec.

    ``generation_model`` optionally pins the Google LLM Memory Bank uses to extract and
    consolidate memories. It must be a Google-published model resource of the form
    ``projects/{project}/locations/{location}/publishers/google/models/{model}``; custom or
    third-party models are not supported by Memory Bank. When ``None``, Memory Bank keeps its
    default model.
    """
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
    memory_bank_config: dict[str, Any] = {
        "structured_memory_configs": [
            {
                "scope_keys": list(scope_keys),
                "schema_configs": sorted(configs, key=lambda item: item["id"]),
            }
            for scope_keys, configs in sorted(grouped.items())
        ]
    }
    if generation_model:
        memory_bank_config["generation_config"] = {"model": generation_model}
    return {"memory_bank_config": memory_bank_config}


class VertexContextProvisioner:
    """Apply active control-plane schemas to an existing Agent Platform resource."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        resource_id: str,
        generation_model: str | None = None,
    ) -> None:
        if not project.strip() or not resource_id.strip():
            raise ValueError(
                "Vertex provisioning requires a project and Agent Platform resource ID"
            )
        self.project = project
        self.location = location
        self.resource_id = resource_id
        self.generation_model = generation_model

    def _generation_model_resource(self) -> str | None:
        """Resolve a configured model into a Google publisher model resource name.

        Accepts either a bare model id (e.g. ``gemini-2.5-flash``) or a full
        ``projects/.../publishers/google/models/...`` resource path.
        """
        model = (self.generation_model or "").strip()
        if not model:
            return None
        if model.startswith("projects/"):
            return model
        return (
            f"projects/{self.project}/locations/{self.location}"
            f"/publishers/google/models/{model}"
        )

    async def provision(self, session: AsyncSession) -> dict[str, Any]:
        context_spec = await build_vertex_context_spec(
            session, generation_model=self._generation_model_resource()
        )
        resource_name = (
            f"projects/{self.project}/locations/{self.location}/reasoningEngines/{self.resource_id}"
        )

        def update() -> str:
            import agentplatform

            client = agentplatform.Client(project=self.project, location=self.location)
            # agentplatform 2.x updates the reasoning engine's context spec through
            # ``runtimes.update`` (the 1.x ``agent_engines.update`` accessor was removed).
            result = client.runtimes.update(
                name=resource_name,
                config={"context_spec": context_spec},
            )
            return str(
                getattr(result, "name", None)
                or getattr(getattr(result, "api_resource", None), "name", resource_name)
            )

        updated_resource = await asyncio.to_thread(update)
        return {
            "status": "PROVISIONED",
            "backend": "VertexMemoryBankStore",
            "resource": updated_resource,
            "generationModel": self._generation_model_resource() or "provider-default",
            "profileInstancesCreated": 0,
            "message": "Active profile schemas were applied; user profiles remain lazy.",
        }
