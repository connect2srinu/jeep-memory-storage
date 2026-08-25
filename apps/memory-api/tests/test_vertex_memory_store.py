from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import pytest_asyncio
from memory_api.domain.memory import MemoryEvent, MemoryProfileSchema, PreferenceWrite
from memory_api.integrations.vertex_memory_store import VertexMemoryBankStore
from memory_api.services.scope_registry import ScopeRegistry


@dataclass
class Operation:
    name: str


class FakeMemoryBankClient:
    def __init__(self) -> None:
        self.memories: dict[tuple[tuple[str, str], ...], list[object]] = {}
        self.profiles: dict[tuple[tuple[str, str], ...], dict[str, object]] = {}
        self.scopes: list[dict[str, str]] = []
        self.ingested: list[str] = []

    @staticmethod
    def key(scope: dict[str, str]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(scope.items()))

    def retrieve_profiles(self, *, scope: dict[str, str]):
        self.scopes.append(scope)
        return SimpleNamespace(profiles=self.profiles.get(self.key(scope), {}))

    def retrieve(self, *, scope: dict[str, str]) -> list[object]:
        self.scopes.append(scope)
        return list(self.memories.get(self.key(scope), []))

    def create(self, *, fact: str, scope: dict[str, str]):
        self.scopes.append(scope)
        memory = SimpleNamespace(name=f"memories/{len(self.memories) + 1}", fact=fact)
        self.memories.setdefault(self.key(scope), []).append(SimpleNamespace(memory=memory))
        return Operation(memory.name)

    def ingest_event(self, *, text: str, scope: dict[str, str], stream_id: str):
        self.scopes.append(scope)
        self.ingested.append(f"{stream_id}:{text}")
        return Operation("operations/ingest")


@pytest.fixture
def scope():
    return ScopeRegistry().resolve(
        "organization-user-profile",
        {"organization_id": "retail", "user_id": "1001"},
    )


@pytest_asyncio.fixture
async def store():
    client = FakeMemoryBankClient()
    backend = VertexMemoryBankStore(client)
    await backend.register_schema(
        MemoryProfileSchema(
            id="grocery-preferences-v1",
            domain="grocery",
            version="1",
            fields=frozenset({"preferred_snack"}),
        )
    )
    return backend, client


@pytest.mark.asyncio
async def test_retrieve_profiles_uses_exact_scope_and_filters_schema(store, scope) -> None:
    backend, client = store
    client.profiles[client.key(VertexMemoryBankStore._scope(scope))] = {
        "grocery-preferences-v1": SimpleNamespace(
            profile={"preferred_snack": "mango chips", "unknown": "rejected"}
        ),
        "not-authorized": SimpleNamespace(profile={"value": "hidden"}),
    }

    profiles = await backend.get_profiles(scope, ("grocery-preferences-v1",))

    assert profiles[0].values == {"preferred_snack": "mango chips"}
    assert all(set(item) == {"organization_id", "user_id"} for item in client.scopes)


@pytest.mark.asyncio
async def test_explicit_write_overlays_provider_profile_and_increments_version(
    store, scope
) -> None:
    backend, client = store
    first = await backend.write_preference(
        scope,
        schema_id="grocery-preferences-v1",
        attribute="preferred_snack",
        value="mango chips",
    )
    second = await backend.write_preference(
        scope,
        schema_id="grocery-preferences-v1",
        attribute="preferred_snack",
        value="potato chips",
    )
    profiles = await backend.get_profiles(scope, ("grocery-preferences-v1",))

    assert first.version == 1
    assert second.version == 2
    assert profiles[0].values == {"preferred_snack": "potato chips"}
    facts = [
        json.loads(item.memory.fact) for item in client.memories[client.key(backend._scope(scope))]
    ]
    assert {item["schema"] for item in facts} == {backend._EXPLICIT_SCHEMA}


@pytest.mark.asyncio
async def test_event_preserves_candidate_write_and_triggers_lazy_generation(store, scope) -> None:
    backend, client = store
    result = await backend.ingest_event(
        scope,
        MemoryEvent(
            text="I prefer mango chips.",
            candidates=(
                PreferenceWrite("grocery-preferences-v1", "preferred_snack", "mango chips"),
            ),
        ),
    )

    assert result.updated_profiles[0].values == {"preferred_snack": "mango chips"}
    assert client.ingested == ["retail-1001:I prefer mango chips."]
    natural = await backend.get_natural_memories(scope)
    assert natural[0].text == "I prefer mango chips."


@pytest.mark.asyncio
async def test_cross_organization_profiles_are_isolated(store, scope) -> None:
    backend, _ = store
    await backend.write_preference(
        scope,
        schema_id="grocery-preferences-v1",
        attribute="preferred_snack",
        value="mango chips",
    )
    other_organization_scope = ScopeRegistry().resolve(
        "organization-user-profile",
        {"organization_id": "healthcare", "user_id": "1001"},
    )
    assert await backend.get_profiles(other_organization_scope, ("grocery-preferences-v1",)) == ()
