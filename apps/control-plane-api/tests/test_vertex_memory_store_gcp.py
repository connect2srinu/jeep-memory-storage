from __future__ import annotations

import os
from uuid import uuid4

import pytest
from control_plane_api.domain.memory import MemoryEvent, MemoryProfileSchema
from control_plane_api.integrations.vertex_memory_store import VertexMemoryBankStore
from control_plane_api.services.scope_registry import ScopeRegistry

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GCP_INTEGRATION_TESTS") != "1",
    reason="requires explicit GCP integration-test opt in",
)


@pytest.mark.asyncio
async def test_vertex_exact_scope_retrieve_and_event_generation() -> None:
    store = VertexMemoryBankStore.from_config(
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        resource_id=os.environ["AGENT_PLATFORM_MEMORY_BANK_ID"],
    )
    schema_id = os.getenv("GCP_TEST_PROFILE_SCHEMA_ID", "grocery-preferences-v1")
    await store.register_schema(
        MemoryProfileSchema(
            id=schema_id,
            domain="grocery",
            version="1",
            fields=frozenset({"preferred_snack"}),
        )
    )
    scope = ScopeRegistry().resolve(
        "domain-profile",
        {
            "user_id": f"phase8-{uuid4()}",
            "app_name": os.getenv("ADK_APP_NAME", "grocery_shared_preferences"),
            "domain": "grocery",
        },
    )

    assert await store.get_profiles(scope, (schema_id,)) == ()
    result = await store.ingest_event(scope, MemoryEvent("I explicitly prefer mango chips."))

    assert result.natural_memory.scope == scope
    assert await store.get_natural_memories(scope)
