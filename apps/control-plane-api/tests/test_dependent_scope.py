"""Option C — dependent-scoped memory: scope plumbing, store isolation, and service routing."""

from __future__ import annotations

import pytest
from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.memory import MemoryProfileSchema, MemoryScope
from control_plane_api.domain.runtime import RuntimeSchemaGrant
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.services.runtime_service import RuntimeMemoryService
from control_plane_api.services.scope_registry import ScopeRegistry

DEP_KEYS = ("organization_id", "user_id", "dependent_id")
MEMBER_KEYS = ("organization_id", "user_id")
HH_KEYS = ("organization_id", "household_id")
HH_MEMBER_KEYS = ("organization_id", "household_id", "member_id")


def test_identity_includes_dependent() -> None:
    assert MemoryScope("org", "u1").identity == ("org", "u1")
    assert MemoryScope("org", "u1", "child1").identity == ("org", "u1", "child1")


def test_scope_registry_dependent_contract() -> None:
    reg = ScopeRegistry()
    scope = reg.resolve(
        "organization-user-dependent-profile",
        {"organization_id": "org", "user_id": "u1", "dependent_id": "child1"},
    )
    assert scope.dependent_id == "child1"
    with pytest.raises(ValueError):
        reg.resolve(
            "organization-user-dependent-profile",
            {"organization_id": "org", "user_id": "u1"},  # missing dependent_id
        )


def test_scope_registry_household_contracts() -> None:
    reg = ScopeRegistry()
    shared = reg.resolve(
        "organization-household-profile", {"organization_id": "org", "household_id": "h1"}
    )
    assert shared.identity == ("org", "h1")
    member = reg.resolve(
        "organization-household-member-profile",
        {"organization_id": "org", "household_id": "h1", "member_id": "m1"},
    )
    assert member.identity == ("org", "h1", "m1")


@pytest.mark.asyncio
async def test_mock_store_isolates_household_members() -> None:
    store = MockMemoryStore()
    await store.register_schema(
        MemoryProfileSchema(id="hh", domain="ksa", version="v1", fields=frozenset({"diet"}))
    )
    shared = MemoryScope("org", household_id="h1")
    m1 = MemoryScope("org", household_id="h1", member_id="m1")
    m2 = MemoryScope("org", household_id="h1", member_id="m2")
    await store.write_preference(shared, schema_id="hh", attribute="diet", value="vegetarian")
    await store.write_preference(m1, schema_id="hh", attribute="diet", value="vegan")

    assert (await store.get_profiles(shared, ("hh",)))[0].values["diet"] == "vegetarian"
    assert (await store.get_profiles(m1, ("hh",)))[0].values["diet"] == "vegan"
    assert await store.get_profiles(m2, ("hh",)) == ()  # a member with no profile is empty

    # A household forget cascades to its members; a member forget targets just that member.
    assert await store.forget_user(m1) == 1
    assert await store.get_profiles(m1, ("hh",)) == ()
    assert (await store.get_profiles(shared, ("hh",)))[0].values["diet"] == "vegetarian"
    assert await store.forget_user(shared) >= 1
    assert await store.get_profiles(shared, ("hh",)) == ()


@pytest.mark.asyncio
async def test_mock_store_isolates_dependents() -> None:
    store = MockMemoryStore()
    await store.register_schema(
        MemoryProfileSchema(id="dep", domain="ksa", version="v1", fields=frozenset({"allergies"}))
    )
    c1 = MemoryScope("org", "u1", "child1")
    c2 = MemoryScope("org", "u1", "child2")
    await store.write_preference(c1, schema_id="dep", attribute="allergies", value="peanut")
    await store.write_preference(c2, schema_id="dep", attribute="allergies", value="none")

    assert (await store.get_profiles(c1, ("dep",)))[0].values["allergies"] == "peanut"
    assert (await store.get_profiles(c2, ("dep",)))[0].values["allergies"] == "none"
    # A member-scope read does not surface a dependent's partition.
    assert await store.get_profiles(MemoryScope("org", "u1"), ("dep",)) == ()


@pytest.mark.asyncio
async def test_member_forget_cascades_dependent_forget_targets() -> None:
    store = MockMemoryStore()
    await store.register_schema(
        MemoryProfileSchema(id="s", domain="ksa", version="v1", fields=frozenset({"a"}))
    )
    member = MemoryScope("org", "u1")
    c1 = MemoryScope("org", "u1", "child1")
    c2 = MemoryScope("org", "u1", "child2")
    await store.write_preference(member, schema_id="s", attribute="a", value="m")
    await store.write_preference(c1, schema_id="s", attribute="a", value="1")
    await store.write_preference(c2, schema_id="s", attribute="a", value="2")

    # Dependent forget removes only that dependent.
    assert await store.forget_user(c1) == 1
    assert await store.get_profiles(c1, ("s",)) == ()
    assert (await store.get_profiles(c2, ("s",)))[0].values["a"] == "2"

    # Member forget cascades to the member and every remaining dependent.
    assert await store.forget_user(member) == 2
    assert await store.get_profiles(member, ("s",)) == ()
    assert await store.get_profiles(c2, ("s",)) == ()


def _service() -> RuntimeMemoryService:
    return RuntimeMemoryService(
        repository=None,  # type: ignore[arg-type]  # scope helpers don't touch the repository
        store=MockMemoryStore(),
        scope_registry=ScopeRegistry(),
    )


def _grant(scope_keys: tuple[str, ...]) -> RuntimeSchemaGrant:
    return RuntimeSchemaGrant(
        schema_id="s",
        owner_organization_id="org",
        domain_id="ksa",
        schema_version="v1",
        permission=AccessPermission.READ_WRITE,
        scope_keys=scope_keys,
        field_to_attribute={"a": "a"},
    )


def test_entity_key() -> None:
    assert RuntimeMemoryService._entity_key(_grant(DEP_KEYS)) == "dependent_id"
    assert RuntimeMemoryService._entity_key(_grant(MEMBER_KEYS)) is None
    assert RuntimeMemoryService._entity_key(_grant(HH_MEMBER_KEYS)) == "member_id"


def test_scope_levels() -> None:
    assert RuntimeMemoryService._scope_level(_grant(MEMBER_KEYS)) == "member"
    assert RuntimeMemoryService._scope_level(_grant(DEP_KEYS)) == "dependent"
    assert RuntimeMemoryService._scope_level(_grant(HH_KEYS)) == "household"
    assert RuntimeMemoryService._scope_level(_grant(HH_MEMBER_KEYS)) == "household_member"


def test_build_scope_write_rejects_mismatched_entity_key() -> None:
    with pytest.raises(ValueError, match="not valid"):
        _service()._build_scope(
            organization_id="org",
            scope_keys=MEMBER_KEYS,
            values={"user_id": "u1", "dependent_id": "child1"},
            strict=True,
        )


def test_build_scope_requires_and_builds() -> None:
    svc = _service()
    with pytest.raises(ValueError, match="required"):
        svc._build_scope(
            organization_id="org", scope_keys=DEP_KEYS, values={"user_id": "u1"}, strict=True
        )
    scope = svc._build_scope(
        organization_id="org",
        scope_keys=DEP_KEYS,
        values={"user_id": "u1", "dependent_id": "child1"},
        strict=True,
    )
    assert scope.dependent_id == "child1"
    household = svc._build_scope(
        organization_id="org",
        scope_keys=HH_MEMBER_KEYS,
        values={"household_id": "h1", "member_id": "m1"},
        strict=True,
    )
    assert household.household_id == "h1"
    assert household.member_id == "m1"


def test_build_scope_rejects_unsupported_keys() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        _service()._build_scope(
            organization_id="org",
            scope_keys=("organization_id",),
            values={"user_id": "u1"},
            strict=True,
        )
