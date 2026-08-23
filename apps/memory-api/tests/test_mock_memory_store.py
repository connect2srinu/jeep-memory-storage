from __future__ import annotations

import pytest
import pytest_asyncio
from memory_api.domain.memory import MemoryEvent, MemoryProfileSchema, PreferenceWrite
from memory_api.integrations.mock_memory_store import MockMemoryStore
from memory_api.services.scope_registry import ScopeRegistry


@pytest.fixture
def registry() -> ScopeRegistry:
    return ScopeRegistry()


@pytest_asyncio.fixture
async def store() -> MockMemoryStore:
    backend = MockMemoryStore()
    await backend.register_schema(
        MemoryProfileSchema(
            id="grocery-preferences-v1",
            domain="grocery",
            version="1",
            fields=frozenset({"preferred_snack", "allow_substitutions"}),
        )
    )
    return backend


def test_scope_registry_requires_exact_keys(registry: ScopeRegistry) -> None:
    with pytest.raises(ValueError, match="missing=.*domain"):
        registry.resolve("domain-profile", {"user_id": "u1", "app_name": "grocery"})


@pytest.mark.asyncio
async def test_event_lazily_creates_profile_and_natural_memory(
    store: MockMemoryStore, registry: ScopeRegistry
) -> None:
    scope = registry.resolve(
        "domain-profile", {"user_id": "u1", "app_name": "grocery", "domain": "grocery"}
    )
    result = await store.ingest_event(
        scope,
        MemoryEvent(
            text="I prefer mango chips.",
            candidates=(
                PreferenceWrite("grocery-preferences-v1", "preferred_snack", "mango chips"),
            ),
        ),
    )

    assert result.updated_profiles[0].values == {"preferred_snack": "mango chips"}
    assert await store.get_natural_memories(scope) == (result.natural_memory,)


@pytest.mark.asyncio
async def test_explicit_write_updates_version_without_cross_user_leakage(
    store: MockMemoryStore, registry: ScopeRegistry
) -> None:
    first = registry.resolve(
        "domain-profile", {"user_id": "u1", "app_name": "grocery", "domain": "grocery"}
    )
    second = registry.resolve(
        "domain-profile", {"user_id": "u2", "app_name": "grocery", "domain": "grocery"}
    )
    created = await store.write_preference(
        first,
        schema_id="grocery-preferences-v1",
        attribute="preferred_snack",
        value="mango chips",
    )
    updated = await store.write_preference(
        first,
        schema_id="grocery-preferences-v1",
        attribute="preferred_snack",
        value="potato chips",
    )

    assert created.version == 1
    assert updated.version == 2
    assert await store.get_profiles(second, ("grocery-preferences-v1",)) == ()


@pytest.mark.asyncio
async def test_schema_and_domain_guards_are_default_deny(
    store: MockMemoryStore, registry: ScopeRegistry
) -> None:
    customer_scope = registry.resolve(
        "domain-profile", {"user_id": "u1", "app_name": "grocery", "domain": "customer"}
    )
    with pytest.raises(PermissionError, match="domain"):
        await store.write_preference(
            customer_scope,
            schema_id="grocery-preferences-v1",
            attribute="preferred_snack",
            value="mango chips",
        )
