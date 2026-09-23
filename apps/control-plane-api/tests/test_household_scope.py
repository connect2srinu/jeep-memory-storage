"""Household memory: scope plumbing, store isolation, and service routing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.memory import MemoryProfileSchema, MemoryScope
from control_plane_api.domain.runtime import RuntimeSchemaGrant
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.services.runtime_service import RuntimeMemoryService
from control_plane_api.services.scope_registry import ScopeRegistry

MEMBER_KEYS = ("organization_id", "user_id")
HH_KEYS = ("organization_id", "household_id")
HH_MEMBER_KEYS = ("organization_id", "household_id", "member_id")


def test_identity_reflects_present_keys() -> None:
    assert MemoryScope("org", "u1").identity == ("org", "u1")
    assert MemoryScope("org", household_id="h1").identity == ("org", "h1")
    assert MemoryScope("org", household_id="h1", member_id="m1").identity == ("org", "h1", "m1")


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
    with pytest.raises(ValueError):
        reg.resolve(
            "organization-household-member-profile",
            {"organization_id": "org", "household_id": "h1"},  # missing member_id
        )


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

    # A member forget targets just that member; a household forget cascades to its members.
    assert await store.forget_user(m1) == 1
    assert await store.get_profiles(m1, ("hh",)) == ()
    assert (await store.get_profiles(shared, ("hh",)))[0].values["diet"] == "vegetarian"
    assert await store.forget_user(shared) >= 1
    assert await store.get_profiles(shared, ("hh",)) == ()


@pytest.mark.asyncio
async def test_mock_store_deletes_one_attribute_and_purges_by_age() -> None:
    store = MockMemoryStore()
    await store.register_schema(
        MemoryProfileSchema(
            id="hm", domain="ksa", version="v1", fields=frozenset({"allergies", "dislikes"})
        )
    )
    kid = MemoryScope("org", household_id="h1", member_id="m1")
    await store.write_preference(kid, schema_id="hm", attribute="allergies", value="peanut")
    await store.write_preference(kid, schema_id="hm", attribute="dislikes", value="kale")

    # Only the named attribute in exactly this scope goes.
    assert await store.delete_preference(kid, schema_id="hm", attribute="allergies") == 1
    assert (await store.get_profiles(kid, ("hm",)))[0].values == {"dislikes": "kale"}

    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=1)
    assert await store.purge(organization_id="org", schema_id="hm", older_than=past) == ()
    preview = await store.purge(
        organization_id="org", schema_id="hm", older_than=future, dry_run=True
    )
    assert [entry["attribute"] for entry in preview] == ["dislikes"]
    assert await store.get_profiles(kid, ("hm",)) != ()
    await store.purge(organization_id="org", schema_id="hm", older_than=future)
    assert await store.get_profiles(kid, ("hm",)) == ()


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
    assert RuntimeMemoryService._entity_key(_grant(MEMBER_KEYS)) is None
    assert RuntimeMemoryService._entity_key(_grant(HH_KEYS)) is None
    assert RuntimeMemoryService._entity_key(_grant(HH_MEMBER_KEYS)) == "member_id"


def test_scope_levels() -> None:
    assert RuntimeMemoryService._scope_level(_grant(MEMBER_KEYS)) == "member"
    assert RuntimeMemoryService._scope_level(_grant(HH_KEYS)) == "household"
    assert RuntimeMemoryService._scope_level(_grant(HH_MEMBER_KEYS)) == "household_member"


def test_build_scope_write_rejects_mismatched_entity_key() -> None:
    # A memberId on a household-shared attribute is rejected on writes.
    with pytest.raises(ValueError, match="not valid"):
        _service()._build_scope(
            organization_id="org",
            scope_keys=HH_KEYS,
            values={"household_id": "h1", "member_id": "m1"},
            strict=True,
        )


def test_build_scope_requires_and_builds() -> None:
    svc = _service()
    with pytest.raises(ValueError, match="required"):
        svc._build_scope(
            organization_id="org", scope_keys=HH_MEMBER_KEYS, values={"household_id": "h1"},
            strict=True,
        )
    member = svc._build_scope(
        organization_id="org",
        scope_keys=HH_MEMBER_KEYS,
        values={"household_id": "h1", "member_id": "m1"},
        strict=True,
    )
    assert member.household_id == "h1"
    assert member.member_id == "m1"


def test_build_scope_rejects_unsupported_keys() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        _service()._build_scope(
            organization_id="org",
            scope_keys=("organization_id",),
            values={"user_id": "u1"},
            strict=True,
        )
