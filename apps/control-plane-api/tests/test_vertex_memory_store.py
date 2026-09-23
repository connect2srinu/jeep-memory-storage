from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from control_plane_api.domain.memory import MemoryEvent, MemoryProfileSchema, PreferenceWrite
from control_plane_api.integrations.vertex_memory_store import VertexMemoryBankStore
from control_plane_api.services.scope_registry import ScopeRegistry


@dataclass
class Operation:
    name: str


class FakeMemoryBankClient:
    def __init__(self) -> None:
        self.memories: dict[tuple[tuple[str, str], ...], list[object]] = {}
        self.profiles: dict[tuple[tuple[str, str], ...], dict[str, object]] = {}
        self.scopes: list[dict[str, str]] = []
        self.ingested: list[str] = []
        self._counter = 0

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
        self._counter += 1
        memory = SimpleNamespace(name=f"memories/{self._counter}", fact=fact, scope=dict(scope))
        self.memories.setdefault(self.key(scope), []).append(SimpleNamespace(memory=memory))
        return Operation(memory.name)

    def ingest_event(self, *, text: str, scope: dict[str, str], stream_id: str):
        self.scopes.append(scope)
        self.ingested.append(f"{stream_id}:{text}")
        return Operation("operations/ingest")

    def delete(self, *, name: str):
        for items in self.memories.values():
            items[:] = [it for it in items if getattr(it.memory, "name", None) != name]
        return Operation(name)

    def list_memories(self) -> list[object]:
        return [item for items in self.memories.values() for item in items]


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
async def test_event_preserves_candidate_write_but_never_triggers_managed_generation(
    store, scope
) -> None:
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
    # Managed generation is disabled: the provider's ingest_events must never be called, so it
    # cannot extract arbitrary, ungoverned memories.
    assert client.ingested == []
    natural = await backend.get_natural_memories(scope)
    assert natural[0].text == "I prefer mango chips."


@pytest.mark.asyncio
async def test_distinct_attributes_survive_newest_first_retrieval(scope) -> None:
    # Real Memory Bank returns memories newest-first. Each explicit write is its own
    # single-attribute memory with a per-schema monotonic version, so overlay reconstruction
    # must keep the highest version *per attribute* — otherwise a newer write to one attribute
    # drops every older attribute of the same schema.
    client = FakeMemoryBankClient()
    backend = VertexMemoryBankStore(client)
    await backend.register_schema(
        MemoryProfileSchema(
            id="grocery-preferences-v1",
            domain="grocery",
            version="1",
            fields=frozenset({"preferred_brand", "preferred_milk"}),
        )
    )
    await backend.write_preference(
        scope, schema_id="grocery-preferences-v1", attribute="preferred_brand", value="Kirkland"
    )
    await backend.write_preference(
        scope, schema_id="grocery-preferences-v1", attribute="preferred_milk", value="oat milk"
    )
    key = client.key(backend._scope(scope))
    client.memories[key] = list(reversed(client.memories[key]))

    profiles = await backend.get_profiles(scope, ("grocery-preferences-v1",))

    assert profiles[0].values == {"preferred_brand": "Kirkland", "preferred_milk": "oat milk"}
    assert profiles[0].version == 2


@pytest.mark.asyncio
async def test_dynamic_memories_keep_latest_per_topic_and_filter_unapproved(scope) -> None:
    client = FakeMemoryBankClient()
    backend = VertexMemoryBankStore(client)
    await backend.write_dynamic_memory(scope, topic="shopping", value="weekly bulk run", confidence=0.9)
    await backend.write_dynamic_memory(scope, topic="shopping", value="fortnightly bulk run", confidence=0.95)
    await backend.write_dynamic_memory(scope, topic="fulfillment", value="leave at door", confidence=0.8)
    # A memory the provider might return newest-first must not drop other topics.
    key = client.key(backend._scope(scope))
    client.memories[key] = list(reversed(client.memories[key]))

    # Only approved topics are returned; the latest version per topic wins.
    memories = await backend.get_dynamic_memories(scope, ("shopping", "fulfillment"))
    by_topic = {m.topic: m.value for m in memories}
    assert by_topic == {"shopping": "fortnightly bulk run", "fulfillment": "leave at door"}

    # An unapproved topic is filtered out even though it is stored.
    await backend.write_dynamic_memory(scope, topic="health", value="allergic to shellfish", confidence=0.99)
    filtered = await backend.get_dynamic_memories(scope, ("shopping", "fulfillment"))
    assert "health" not in {m.topic for m in filtered}


@pytest.mark.asyncio
async def test_forget_deletes_and_purge_targets_by_topic(scope) -> None:
    client = FakeMemoryBankClient()
    backend = VertexMemoryBankStore(client)
    await backend.register_schema(
        MemoryProfileSchema(
            id="grocery-preferences-v1",
            domain="grocery",
            version="1",
            fields=frozenset({"preferred_snack", "shopping", "fulfillment"}),
        )
    )
    other = ScopeRegistry().resolve(
        "organization-user-profile", {"organization_id": "retail", "user_id": "2002"}
    )
    await backend.write_preference(
        scope, schema_id="grocery-preferences-v1", attribute="preferred_snack", value="mango"
    )
    await backend.write_dynamic_memory(scope, topic="shopping", value="sunday", confidence=0.9)
    await backend.write_dynamic_memory(other, topic="shopping", value="monday", confidence=0.9)

    # Operator purge, dry run: both users match, nothing removed.
    preview = await backend.purge(organization_id="retail", topic="shopping", dry_run=True)
    assert {m["userId"] for m in preview} == {"1001", "2002"}
    assert len(await backend.get_dynamic_memories(scope, ("shopping",))) == 1

    # Execute: the topic is removed for the whole org, canonical is untouched.
    purged = await backend.purge(organization_id="retail", topic="shopping", dry_run=False)
    assert len(purged) == 2
    assert await backend.get_dynamic_memories(scope, ("shopping",)) == ()
    assert (await backend.get_profiles(scope, ("grocery-preferences-v1",)))[0].values == {
        "preferred_snack": "mango"
    }

    # Forget removes everything left for the one user.
    deleted = await backend.forget_user(scope)
    assert deleted == 1
    assert await backend.get_profiles(scope, ("grocery-preferences-v1",)) == ()


@pytest.mark.asyncio
async def test_delete_one_attribute_and_purge_by_schema_and_age() -> None:
    client = FakeMemoryBankClient()
    backend = VertexMemoryBankStore(client)
    await backend.register_schema(
        MemoryProfileSchema(
            id="hm", domain="grocery", version="1", fields=frozenset({"allergies", "dislikes"})
        )
    )
    registry = ScopeRegistry()
    kid = registry.resolve(
        "organization-household-member-profile",
        {"organization_id": "retail", "household_id": "h1", "member_id": "m1"},
    )
    sibling = registry.resolve(
        "organization-household-member-profile",
        {"organization_id": "retail", "household_id": "h1", "member_id": "m2"},
    )
    await backend.write_preference(kid, schema_id="hm", attribute="allergies", value="peanut")
    await backend.write_preference(kid, schema_id="hm", attribute="allergies", value="sesame")
    await backend.write_preference(kid, schema_id="hm", attribute="dislikes", value="kale")
    await backend.write_preference(sibling, schema_id="hm", attribute="allergies", value="egg")

    # Every stored version of one attribute goes, only in exactly that member's scope.
    assert await backend.delete_preference(kid, schema_id="hm", attribute="allergies") == 1
    assert (await backend.get_profiles(kid, ("hm",)))[0].values == {"dislikes": "kale"}
    assert (await backend.get_profiles(sibling, ("hm",)))[0].values == {"allergies": "egg"}

    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=1)
    assert await backend.purge(organization_id="retail", schema_id="hm", older_than=past) == ()
    expired = await backend.purge(organization_id="retail", schema_id="hm", older_than=future)
    assert {entry["attribute"] for entry in expired} == {"dislikes", "allergies"}
    assert await backend.get_profiles(kid, ("hm",)) == ()


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
