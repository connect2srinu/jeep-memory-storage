"""Dynamic household members end to end: setup through the guided API, then runtime writes that
resolve, propose, confirm and govern household members."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from control_plane_api.application import create_app
from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.persistence import Database
from db_seed import seed_control_plane

PLATFORM = {"X-Admin-User": "platform@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}
AGENT = {"X-Agent-ID": "familygrocery-assistant"}
DOMAIN = "familygrocery"

PREFERENCES = [
    # (field, level, health, description)
    ("organic_brand", "household", False, "Preferred organic brand"),
    ("preferred_store", "household", False, "Store the household shops at"),
    ("allow_substitutions", "household", False, "Whether substitutions are allowed"),
    ("preferred_size", "household", False, "Preferred pack size"),
    ("excluded_products", "household", False, "Products to exclude from household orders"),
    ("dislikes", "member", False, "Foods this person does not like"),
    ("allergies", "member", True, "This person's food allergies"),
]


def setup_payload(retention: int | None = 365) -> dict[str, object]:
    return {
        "useCase": {
            "name": "Family Grocery",
            "description": "Household preferences with per-member dislikes and allergies",
            "owningTeam": "grocery-platform",
            "organizationId": "retail",
            "projectId": "shopping",
            "domain": DOMAIN,
            "environment": "development",
        },
        "selectedPreferences": [],
        "customPreferences": [
            {
                "attributeId": f"{DOMAIN}.{field}",
                "displayName": field.replace("_", " ").title(),
                "description": description,
                "dataType": "string",
                "sensitivity": "normal",
                "level": level,
                "isHealth": health,
            }
            for field, level, health, description in PREFERENCES
        ],
        "scope": {"type": "HOUSEHOLD_MEMBERS", "customKeys": []},
        "memory": {
            "canonical": True,
            "dynamicEnabled": False,
            "confirmationRequired": False,
            "profileRetentionDays": retention,
        },
        "agent": {
            "id": "familygrocery-assistant",
            "displayName": "Family Grocery Assistant",
            "ownedSchemaPermission": "READ_WRITE",
        },
        "resolution": {
            "schemaPrecedence": [
                f"{DOMAIN}-household-preferences-v1",
                f"{DOMAIN}-member-preferences-v1",
            ],
            "attributeOverrides": [],
        },
    }


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'dynamic.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused", auth_enabled=False, google_id_token_audience=None
        ),
        database=database,
        store=MockMemoryStore(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        activated = await http.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=setup_payload()
        )
        assert activated.status_code == 201, activated.text
        yield http
    await database.dispose()


def scope(user: str = "priya", **extra: str) -> dict[str, str]:
    return {"userId": user, "domain": DOMAIN, **extra}


async def save(http, attribute: str, value: str, user: str = "priya", **body):
    member_id = body.pop("memberId", None)
    response = await http.put(
        f"/api/v1/runtime/preferences/{DOMAIN}.{attribute}",
        headers=AGENT,
        json={
            "scope": scope(user, **({"memberId": member_id} if member_id else {})),
            "value": value,
            **body,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def resolve(http, user: str = "priya", member_id: str | None = None):
    response = await http.post(
        "/api/v1/runtime/preferences/resolve",
        headers=AGENT,
        json={
            "scope": scope(user, **({"memberId": member_id} if member_id else {})),
            "sessionId": "s",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def add_member(http, name: str, relationship: str, user: str = "priya") -> str:
    response = await http.post(
        "/api/v1/runtime/household/members",
        headers=AGENT,
        json={"scope": scope(user), "name": name, "relationship": relationship, "confirmed": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "added", response.text
    return response.json()["memberId"]


def roster(snapshot) -> dict[str, dict]:
    return {m["displayName"] or "self": m for m in snapshot["householdMembers"]}


@pytest.mark.asyncio
async def test_first_use_creates_the_household_root(client) -> None:
    first = await resolve(client)
    assert first["householdId"].startswith("hh_")
    [member] = first["householdMembers"]
    assert member["isSelf"] and member["memberKind"] == "ROOT"
    assert member["memberId"] == first["actingMemberId"] != "priya"
    assert (await resolve(client))["householdId"] == first["householdId"]
    health = {d["attribute"]: d["health"] for d in first["writablePreferenceDetails"]}
    assert health[f"{DOMAIN}.allergies"] and not health[f"{DOMAIN}.dislikes"]


@pytest.mark.asyncio
async def test_new_member_is_proposed_then_confirmed(client) -> None:
    proposed = await save(client, "dislikes", "peanuts", memberName="Ryan", relationship="son")
    assert proposed["status"] == "needs_confirmation"
    assert proposed["confirmationPrompt"] == (
        'Should I add Ryan (your son) to your household and save their dislikes as "peanuts"?'
    )
    assert roster(await resolve(client))["Ryan"]["status"] == "provisional"

    saved = await save(
        client, "dislikes", "peanuts", memberId=proposed["memberId"], confirmed=True
    )
    assert saved["status"] == "updated"
    ryan = roster(await resolve(client))["Ryan"]
    assert (ryan["status"], ryan["memberKind"], ryan["minor"]) == ("active", "DEPENDENT", True)
    values = (await resolve(client, member_id=ryan["memberId"]))["preferences"]
    assert values["dislikes"]["value"] == "peanuts"

    # The next mention matches directly — no second Ryan.
    again = await save(client, "dislikes", "olives", memberName="ryan")
    assert again["status"] == "updated" and again["memberId"] == ryan["memberId"]


@pytest.mark.asyncio
async def test_name_variant_matches_and_is_learned(client) -> None:
    anika = await add_member(client, "Anika", "daughter")
    saved = await save(client, "dislikes", "mushrooms", memberName="Anikaa")
    assert saved["status"] == "updated" and saved["memberId"] == anika
    assert "anikaa" in roster(await resolve(client))["Anika"]["aliases"]


@pytest.mark.asyncio
async def test_relationship_guard_and_ambiguity(client) -> None:
    await add_member(client, "Sam", "son")
    # "Sam, my daughter" is a different person than Sam the son.
    other = await save(client, "dislikes", "kale", memberName="Sam", relationship="daughter")
    assert other["status"] == "needs_confirmation"
    await save(client, "dislikes", "kale", memberId=other["memberId"], confirmed=True)

    unclear = await save(client, "dislikes", "beets", memberName="Sam")
    assert unclear["status"] == "ambiguous"
    assert len(unclear["candidates"]) == 2 and "Which" in unclear["confirmationPrompt"]


@pytest.mark.asyncio
async def test_health_data_requires_confirmation_and_records_consent(client) -> None:
    ryan = await add_member(client, "Ryan", "son")
    asked = await save(client, "allergies", "peanuts", memberName="Ryan")
    assert asked["status"] == "needs_confirmation"
    assert asked["confirmationPrompt"] == (
        'Please confirm: save allergies as "peanuts" for Ryan (your son)?'
    )
    assert "allergies" not in (await resolve(client, member_id=ryan))["preferences"]

    # Confirming a different value than the one asked about does not write.
    other = await save(client, "allergies", "shellfish", memberId=ryan, confirmed=True)
    assert other["status"] == "needs_confirmation"

    saved = await save(client, "allergies", "peanuts", memberId=ryan, confirmed=True)
    assert saved["status"] == "updated"
    assert (await resolve(client, member_id=ryan))["preferences"]["allergies"]["value"] == (
        "peanuts"
    )

    household = (await resolve(client))["householdId"]
    consents = await client.get(
        f"/api/v1/admin/organizations/retail/households/{household}/consents", headers=PLATFORM
    )
    granted = [c for c in consents.json()["items"] if c["status"] == "GRANTED"]
    assert len(granted) == 1
    assert granted[0]["subject_member_id"] == ryan
    assert granted[0]["prompt_text"] == asked["confirmationPrompt"]


@pytest.mark.asyncio
async def test_new_member_and_health_fact_share_one_confirmation(client) -> None:
    asked = await save(client, "allergies", "sesame", memberName="Maya", relationship="daughter")
    assert asked["status"] == "needs_confirmation"
    assert "add Maya (your daughter)" in asked["confirmationPrompt"]
    saved = await save(
        client, "allergies", "sesame", memberId=asked["memberId"], confirmed=True
    )
    assert saved["status"] == "updated"


@pytest.mark.asyncio
async def test_health_data_about_another_adult_is_refused(client) -> None:
    refused = await save(client, "allergies", "shellfish", memberName="Meera", relationship="wife")
    assert refused["status"] == "not_allowed"
    assert "household-level product filter" in refused["message"]
    assert "Meera" not in roster(await resolve(client))  # not proposed either

    meera = await add_member(client, "Meera", "wife")
    assert (await save(client, "allergies", "shellfish", memberId=meera))["status"] == (
        "not_allowed"
    )
    # Non-health preferences for the adult, and the household product filter, are fine.
    assert (await save(client, "dislikes", "cilantro", memberId=meera))["status"] == "updated"
    assert (await save(client, "excluded_products", "shellfish"))["status"] == "updated"

    # Correcting a dependent to an adult switches them to proxy-adult rules.
    ryan = await add_member(client, "Ryan", "son")
    fixed = await client.patch(
        f"/api/v1/runtime/household/members/{ryan}",
        headers=AGENT,
        json={"scope": scope(), "minor": False},
    )
    assert fixed.status_code == 200, fixed.text
    assert (await save(client, "allergies", "peanuts", memberId=ryan))["status"] == "not_allowed"


@pytest.mark.asyncio
async def test_own_health_data_is_confirmed_for_you(client) -> None:
    asked = await save(client, "allergies", "latex")
    assert asked["confirmationPrompt"] == 'Please confirm: save allergies as "latex" for you?'
    assert (await save(client, "allergies", "latex", confirmed=True))["status"] == "updated"
    assert (await resolve(client))["preferences"]["allergies"]["value"] == "latex"


@pytest.mark.asyncio
async def test_customers_cannot_reach_another_household(client) -> None:
    other = (await resolve(client, user="omar"))["householdId"]
    denied = await client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=AGENT,
        json={"scope": scope(householdId=other), "sessionId": "s"},
    )
    assert denied.status_code == 403
    omar_kid = await add_member(client, "Zara", "daughter", user="omar")
    stolen = await client.put(
        f"/api/v1/runtime/preferences/{DOMAIN}.dislikes",
        headers=AGENT,
        json={"scope": scope(memberId=omar_kid), "value": "x"},
    )
    assert stolen.status_code == 403


@pytest.mark.asyncio
async def test_merge_rename_move_and_forget(client) -> None:
    kiki = await add_member(client, "Kiki", "daughter")
    anika = await add_member(client, "Anika", "daughter")
    ryan = await add_member(client, "Ryan", "son")
    await save(client, "dislikes", "mushrooms", memberId=kiki)

    body = {"scope": scope(), "keepMemberId": anika, "mergeMemberId": kiki}
    asked = await client.post("/api/v1/runtime/household/members/merge", headers=AGENT, json=body)
    assert asked.json()["status"] == "needs_confirmation"
    merged = await client.post(
        "/api/v1/runtime/household/members/merge",
        headers=AGENT,
        json={**body, "confirmed": True},
    )
    assert merged.json()["status"] == "merged", merged.text
    members = roster(await resolve(client))
    assert "Kiki" not in members and "kiki" in members["Anika"]["aliases"]
    assert (await resolve(client, member_id=anika))["preferences"]["dislikes"]["value"] == (
        "mushrooms"
    )
    assert (await save(client, "dislikes", "okra", memberName="Kiki"))["memberId"] == anika

    renamed = await client.patch(
        f"/api/v1/runtime/household/members/{anika}",
        headers=AGENT,
        json={"scope": scope(), "displayName": "Annie"},
    )
    assert renamed.status_code == 200
    assert "anika" in roster(await resolve(client))["Annie"]["aliases"]

    # Split: a value saved for the wrong child moves to the right one.
    await save(client, "dislikes", "olives", memberId=ryan)
    move = {"scope": scope(memberId=ryan), "toMemberId": anika}
    path = f"/api/v1/runtime/preferences/{DOMAIN}.dislikes/move"
    assert (await client.post(path, headers=AGENT, json=move)).json()["status"] == (
        "needs_confirmation"
    )
    moved = await client.post(path, headers=AGENT, json={**move, "confirmed": True})
    assert moved.json()["status"] == "moved", moved.text
    assert "dislikes" not in (await resolve(client, member_id=ryan))["preferences"]
    assert (await resolve(client, member_id=anika))["preferences"]["dislikes"]["value"] == "olives"

    # Forgetting health data deletes it and withdraws its consent.
    await save(client, "allergies", "peanuts", memberId=ryan)
    await save(client, "allergies", "peanuts", memberId=ryan, confirmed=True)
    forgotten = await client.post(
        f"/api/v1/runtime/preferences/{DOMAIN}.allergies/forget",
        headers=AGENT,
        json={"scope": scope(memberId=ryan)},
    )
    assert forgotten.json()["status"] == "forgotten"
    assert "1 consent record(s) withdrawn" in forgotten.json()["message"]
    assert "allergies" not in (await resolve(client, member_id=ryan))["preferences"]


@pytest.mark.asyncio
async def test_advertising_purpose_is_denied(client) -> None:
    created = await client.post(
        "/api/v1/admin/agents",
        headers=PLATFORM,
        json={
            "id": "ads-agent",
            "displayName": "Ads Agent",
            "organizationId": "retail",
            "projectId": "shopping",
            "domainId": DOMAIN,
            "runtimeType": "OTHER",
            "identityType": "LOCAL_POC",
            "capabilities": {"resolve_context": True},
            "purpose": "advertising",
        },
    )
    assert created.status_code == 201, created.text
    for schema_id, reason in (
        (f"{DOMAIN}-household-preferences-v1", "does not allow"),
        (f"{DOMAIN}-member-preferences-v1", "does not allow"),
    ):
        request = await client.post(
            "/api/v1/admin/access-requests",
            headers=PLATFORM,
            json={
                "requestingAgentId": "ads-agent",
                "requestingTeam": "marketing",
                "targetSchemaId": schema_id,
                "requestedPermission": "READ",
                "businessReason": "Targeted offers",
            },
        )
        assert request.status_code == 201, request.text
        decided = await client.post(
            f"/api/v1/admin/access-requests/{request.json()['data']['id']}/approve",
            headers=PLATFORM,
            json={},
        )
        assert decided.status_code == 403, decided.text
        assert reason in decided.json()["message"]


@pytest.mark.asyncio
async def test_retention_limits_and_sweep(client) -> None:
    too_long = setup_payload(retention=800)
    too_long["useCase"]["domain"] = "longgrocery"  # type: ignore[index]
    for item in too_long["customPreferences"]:  # type: ignore[union-attr]
        item["attributeId"] = item["attributeId"].replace(DOMAIN, "longgrocery")
    too_long["resolution"] = None
    too_long["agent"]["id"] = "long-assistant"  # type: ignore[index]
    preview = await client.post(
        "/api/v1/admin/memory-setups/preview", headers=PLATFORM, json=too_long
    )
    assert preview.status_code == 400
    assert "limit of 730 days for sensitive data" in preview.json()["message"]

    await save(client, "preferred_store", "Kroger")
    proposed = await save(client, "dislikes", "kale", memberName="Leo", relationship="son")
    sweep = "/api/v1/admin/organizations/retail/retention/sweep"
    now_preview = await client.post(sweep, headers=PLATFORM, json={"dryRun": True})
    assert now_preview.json()["data"]["valuesMatched"] == 0

    later = (datetime.now(UTC) + timedelta(days=400)).isoformat()
    future = (await client.post(sweep, headers=PLATFORM, json={"asOf": later})).json()["data"]
    assert future["valuesMatched"] >= 1
    assert any(m["memberId"] == proposed["memberId"] for m in future["provisionalMembers"])

    refused = await client.post(sweep, headers=PLATFORM, json={"dryRun": False, "asOf": later})
    assert refused.status_code == 400
    ran = await client.post(sweep, headers=PLATFORM, json={"dryRun": False})
    assert ran.status_code == 200 and ran.json()["data"]["valuesMatched"] == 0
    assert (await resolve(client))["preferences"]["preferred_store"]["value"] == "Kroger"
