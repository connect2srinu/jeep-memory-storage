from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from control_plane_api.application import create_app
from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.persistence import Database
from control_plane_api.persistence.models import (
    AccessRequestRecord,
    AgentSchemaGrantRecord,
    OrganizationRecord,
    ProfileSchemaRecord,
    ProjectRecord,
    RegisteredAgentRecord,
    ScopeDefinitionRecord,
)
from db_seed import seed_control_plane
from sqlalchemy import select

PLATFORM = {"X-Admin-User": "platform@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}


def setup_payload() -> dict[str, object]:
    return {
        "useCase": {
            "name": "Rewards Personalization",
            "description": "Remember reward choices",
            "owningTeam": "rewards-platform",
            "organizationId": "retail",
            "projectId": "shopping",
            "domain": "rewards",
            "environment": "development",
        },
        "selectedPreferences": ["rewards.reward_type"],
        "customPreferences": [
            {
                "attributeId": "rewards.reward_type",
                "displayName": "Reward Type",
                "description": "Confirmed preferred reward type",
                "dataType": "string",
                "allowedValues": ["points", "cash_back"],
                "sensitivity": "normal",
            }
        ],
        "scope": {"type": "USER", "customKeys": []},
        "memory": {
            "canonical": True,
            "dynamicEnabled": True,
            "confidenceThreshold": 0.85,
            "confirmationRequired": True,
            "retentionDays": 365,
            "memoryTopics": ["rewards"],
        },
        "agent": {
            "id": "rewards-assistant",
            "displayName": "Rewards Assistant",
            "existing": False,
            "runtimeType": "ADK_LOCAL",
            "identityType": "LOCAL_POC",
            "ownedSchemaPermission": "READ_WRITE",
        },
        "sharedSchemas": [{"schemaId": "customer-preferences-v1", "permission": "READ"}],
        "resolution": {
            "schemaPrecedence": ["rewards-preferences-v1", "customer-preferences-v1"],
            "attributeOverrides": [],
        },
    }


@pytest.mark.asyncio
async def test_guided_setup_previews_activates_and_is_immediately_usable(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'guided.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    store = MockMemoryStore()
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused",
            auth_enabled=False,
            google_id_token_audience=None,
        ),
        database=database,
        store=store,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        preview = await client.post(
            "/api/v1/admin/memory-setups/preview", headers=PLATFORM, json=setup_payload()
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["summary"]["profileInstancesCreated"] == 0
        assert "rewards.reward_type" in preview.json()["generatedYaml"]

        activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=setup_payload()
        )
        assert activated.status_code == 201, activated.text
        result = activated.json()
        assert result["status"] == "ACTIVE_WITH_PENDING_ACCESS"
        assert result["provisioning"]["profileInstancesCreated"] == 0
        assert len(result["pendingApprovals"]) == 1

        updated = await client.put(
            "/api/v1/runtime/preferences/rewards.reward_type",
            headers={"X-Agent-ID": "rewards-assistant"},
            json={
                "scope": {
                    "userId": "guided-user-1",
                    "appName": "rewards-demo",
                    "domain": "rewards",
                },
                "schemaId": "rewards-preferences-v1",
                "value": "points",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "updated"

        grocery = setup_payload()
        grocery["useCase"] = {
            "name": "Grocery Personalization",
            "description": "Guided setup over the existing Grocery profile",
            "owningTeam": "grocery-platform",
            "organizationId": "retail",
            "projectId": "shopping",
            "domain": "grocery",
            "environment": "development",
        }
        grocery["selectedPreferences"] = [
            "grocery.dietary_preference",
            "grocery.preferred_store",
            "grocery.allow_substitutions",
            "customer.fulfillment_preference",
        ]
        grocery["customPreferences"] = []
        grocery["agent"] = {
            "id": "grocery-assistant",
            "displayName": "Grocery Assistant",
            "existing": False,
            "runtimeType": "ADK_LOCAL",
            "identityType": "LOCAL_POC",
            "ownedSchemaPermission": "READ_WRITE",
        }
        grocery["resolution"] = {
            "schemaPrecedence": ["grocery-preferences-v1", "customer-preferences-v1"],
            "attributeOverrides": [],
        }
        grocery_activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=grocery
        )
        assert grocery_activated.status_code == 201, grocery_activated.text
        grocery_update = await client.put(
            "/api/v1/runtime/preferences/grocery.allow_substitutions",
            headers={"X-Agent-ID": "grocery-assistant"},
            json={
                "scope": {
                    "userId": "guided-grocery-user",
                    "appName": "grocery-demo",
                    "domain": "grocery",
                },
                "schemaId": "grocery-preferences-v1",
                "value": True,
            },
        )
        assert grocery_update.status_code == 200, grocery_update.text

    async with database.session() as session:
        schema = await session.get(ProfileSchemaRecord, "rewards-preferences-v1")
        scope = await session.get(ScopeDefinitionRecord, "rewards:profile-scope")
        agent = await session.get(RegisteredAgentRecord, "rewards-assistant")
        grant = await session.get(
            AgentSchemaGrantRecord, "rewards-assistant:rewards-preferences-v1"
        )
        pending = list(
            (
                await session.scalars(
                    select(AccessRequestRecord).where(
                        AccessRequestRecord.requesting_agent_id == "rewards-assistant",
                        AccessRequestRecord.status == "PENDING",
                    )
                )
            ).all()
        )
        assert schema is not None and schema.status == "ACTIVE"
        assert scope is not None and scope.status == "ACTIVE"
        assert agent is not None and agent.status == "ACTIVE"
        assert grant is not None and grant.permission == "READ_WRITE" and grant.status == "ACTIVE"
        assert len(pending) == 1
    await database.dispose()


@pytest.mark.asyncio
async def test_guided_setup_auto_creates_missing_organization(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'neworg.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused",
            auth_enabled=False,
            google_id_token_audience=None,
        ),
        database=database,
        store=MockMemoryStore(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = setup_payload()
        payload["useCase"] = {
            "name": "Loyalty Personalization",
            "description": "Bootstraps a brand-new organization",
            "owningTeam": "loyalty-platform",
            "organizationId": "newco",
            "projectId": "loyalty",
            "domain": "loyalty",
            "environment": "development",
        }
        payload["selectedPreferences"] = ["loyalty.tier"]
        payload["customPreferences"] = [
            {
                "attributeId": "loyalty.tier",
                "displayName": "Tier",
                "description": "Confirmed loyalty tier",
                "dataType": "string",
                "allowedValues": ["silver", "gold"],
                "sensitivity": "normal",
            }
        ]
        payload["agent"]["id"] = "loyalty-assistant"
        payload["sharedSchemas"] = []
        payload["resolution"] = None

        activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=payload
        )
        assert activated.status_code == 201, activated.text

    async with database.session() as session:
        org = await session.get(OrganizationRecord, "newco")
        project = await session.get(ProjectRecord, "loyalty")
        assert org is not None and org.status == "ACTIVE"
        assert project is not None and project.organization_id == "newco"
    await database.dispose()


def household_payload() -> dict[str, object]:
    prefs = [
        ("familygrocery.organic_brand", "Organic Brand", "household"),
        ("familygrocery.preferred_store", "Preferred Store", "household"),
        ("familygrocery.allow_substitutions", "Allow Substitutions", "household"),
        ("familygrocery.preferred_size", "Preferred Size", "household"),
        ("familygrocery.allergies", "Allergies", "member"),
    ]
    return {
        "useCase": {
            "name": "Family Grocery",
            "description": "Household grocery preferences with per-member allergies",
            "owningTeam": "grocery-platform",
            "organizationId": "retail",
            "projectId": "shopping",
            "domain": "familygrocery",
            "environment": "development",
        },
        "selectedPreferences": [],
        "customPreferences": [
            {
                "attributeId": attr,
                "displayName": name,
                "description": f"{name} preference",
                "dataType": "string",
                "allowedValues": [],
                "sensitivity": "sensitive" if level == "member" else "normal",
                "level": level,
            }
            for attr, name, level in prefs
        ],
        "scope": {"type": "HOUSEHOLD_MEMBERS", "customKeys": []},
        "memory": {
            "canonical": True,
            "dynamicEnabled": False,
            "confidenceThreshold": 0.85,
            "confirmationRequired": False,
            "retentionDays": 365,
            "memoryTopics": [],
        },
        "agent": {
            "id": "familygrocery-assistant",
            "displayName": "Family Grocery Assistant",
            "existing": False,
            "runtimeType": "ADK_LOCAL",
            "identityType": "LOCAL_POC",
            "ownedSchemaPermission": "READ_WRITE",
        },
        "sharedSchemas": [],
        "resolution": {
            "schemaPrecedence": [
                "familygrocery-household-preferences-v1",
                "familygrocery-member-preferences-v1",
            ],
            "attributeOverrides": [],
        },
    }


@pytest.mark.asyncio
async def test_guided_setup_household_two_tier(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'household.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    store = MockMemoryStore()
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused",
            auth_enabled=False,
            google_id_token_audience=None,
        ),
        database=database,
        store=store,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = household_payload()
        preview = await client.post(
            "/api/v1/admin/memory-setups/preview", headers=PLATFORM, json=payload
        )
        assert preview.status_code == 200, preview.text
        yaml_text = preview.json()["generatedYaml"]
        assert "familygrocery.allergies" in yaml_text
        assert "familygrocery.preferred_store" in yaml_text

        activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=payload
        )
        assert activated.status_code == 201, activated.text
        resources = activated.json()["resources"]
        assert set(resources["schemaIds"]) == {
            "familygrocery-household-preferences-v1",
            "familygrocery-member-preferences-v1",
        }

        household_write = await client.put(
            "/api/v1/runtime/preferences/familygrocery.preferred_store",
            headers={"X-Agent-ID": "familygrocery-assistant"},
            json={
                "scope": {"userId": "alice", "domain": "familygrocery"},
                "schemaId": "familygrocery-household-preferences-v1",
                "value": "Kroger",
            },
        )
        assert household_write.status_code == 200, household_write.text

        member_write = await client.put(
            "/api/v1/runtime/preferences/familygrocery.allergies",
            headers={"X-Agent-ID": "familygrocery-assistant"},
            json={
                # No memberId: a per-member value about the customer themself.
                "scope": {"userId": "alice", "domain": "familygrocery"},
                "schemaId": "familygrocery-member-preferences-v1",
                "value": "peanuts",
            },
        )
        assert member_write.status_code == 200, member_write.text

    async with database.session() as session:
        household_scope = await session.get(ScopeDefinitionRecord, "familygrocery:household-scope")
        member_scope = await session.get(
            ScopeDefinitionRecord, "familygrocery:household-member-scope"
        )
        assert household_scope is not None
        assert list(household_scope.scope_keys) == ["organization_id", "household_id"]
        assert member_scope is not None
        assert list(member_scope.scope_keys) == ["organization_id", "household_id", "member_id"]
        for schema_id in (
            "familygrocery-household-preferences-v1",
            "familygrocery-member-preferences-v1",
        ):
            grant = await session.get(
                AgentSchemaGrantRecord, f"familygrocery-assistant:{schema_id}"
            )
            assert grant is not None
            assert grant.permission == "READ_WRITE" and grant.status == "ACTIVE"
    await database.dispose()


@pytest.mark.asyncio
async def test_shared_schema_request_carries_only_the_ticked_attributes(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'guided-attributes.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused", auth_enabled=False, google_id_token_audience=None
        ),
        database=database,
        store=MockMemoryStore(),
    )
    payload = setup_payload()
    payload["selectedPreferences"] = ["rewards.reward_type", "customer.preferred_store"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Write access to a shared schema needs at least one of its preferences ticked.
        untargeted_write = await client.post(
            "/api/v1/admin/memory-setups/preview",
            headers=PLATFORM,
            json={
                **payload,
                "selectedPreferences": ["rewards.reward_type"],
                "sharedSchemas": [{"schemaId": "customer-preferences-v1", "permission": "READ_WRITE"}],
            },
        )
        assert untargeted_write.status_code == 400
        assert "only ticked preferences can be written" in untargeted_write.text

        activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=payload
        )
        assert activated.status_code == 201, activated.text
        requests = await client.get("/api/v1/admin/access-requests", headers=PLATFORM)
        [shared] = [
            item
            for item in requests.json()["items"]
            if item["requesting_agent_id"] == "rewards-assistant"
            and item["target_schema_id"] == "customer-preferences-v1"
        ]
        assert shared["attributes"] == ["customer.preferred_store"]
    await database.dispose()


@pytest.mark.asyncio
async def test_consumer_only_agent_owns_nothing_and_reads_only_what_is_approved(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'consumer-only.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    store = MockMemoryStore()
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused", auth_enabled=False, google_id_token_audience=None
        ),
        database=database,
        store=store,
    )
    payload = setup_payload()
    payload["useCase"]["domain"] = "mealplanner"
    payload["agent"]["id"] = "mealplanner-assistant"
    payload["selectedPreferences"] = ["customer.preferred_store", "customer.fulfillment_preference"]
    payload["customPreferences"] = []
    payload["resolution"] = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with_dynamic = await client.post(
            "/api/v1/admin/memory-setups/preview", headers=PLATFORM, json=payload
        )
        assert with_dynamic.status_code == 400
        assert "disable dynamic memory" in with_dynamic.text

        payload["memory"]["dynamicEnabled"] = False
        no_sharing = await client.post(
            "/api/v1/admin/memory-setups/preview",
            headers=PLATFORM,
            json={**payload, "sharedSchemas": []},
        )
        assert no_sharing.status_code == 400

        activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=payload
        )
        assert activated.status_code == 201, activated.text
        result = activated.json()
        assert result["summary"]["consumerOnly"] is True
        assert result["resources"]["schemaIds"] == []
        [request_id] = result["pendingApprovals"]

        # Seed values in the customer schema, then approve only one of the two requested.
        for attribute, value in {
            "customer.preferred_store": "Store-B",
            "customer.fulfillment_preference": "pickup",
        }.items():
            saved = await client.put(
                f"/api/v1/runtime/preferences/{attribute}",
                headers={"X-Agent-ID": "customer-agent"},
                json={
                    "scope": {"userId": "meal-user", "appName": "meals", "domain": "customer"},
                    "schemaId": "customer-preferences-v1",
                    "value": value,
                },
            )
            assert saved.status_code == 200, saved.text
        approved = await client.post(
            f"/api/v1/admin/access-requests/{request_id}/approve",
            headers=PLATFORM,
            json={"attributes": ["customer.fulfillment_preference"]},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["attributes"] == [
            "customer.fulfillment_preference",
            "customer.preferred_store",
        ]
        assert approved.json()["data"]["approved_attributes"] == [
            "customer.fulfillment_preference"
        ]

        resolved = await client.post(
            "/api/v1/runtime/preferences/resolve",
            headers={"X-Agent-ID": "mealplanner-assistant"},
            json={
                "scope": {"userId": "meal-user", "appName": "meals", "domain": "mealplanner"},
                "sessionId": "meal-session",
            },
        )
        assert resolved.status_code == 200, resolved.text
        snapshot = resolved.json()
        assert snapshot["preferences"]["fulfillment_preference"]["value"] == "pickup"
        assert "preferred_store" not in snapshot["preferences"]
        assert snapshot["writablePreferences"] == []

        write = await client.put(
            "/api/v1/runtime/preferences/customer.fulfillment_preference",
            headers={"X-Agent-ID": "mealplanner-assistant"},
            json={
                "scope": {"userId": "meal-user", "appName": "meals", "domain": "mealplanner"},
                "value": "delivery",
            },
        )
        assert write.status_code == 403
    async with database.session() as session:
        agent = await session.get(RegisteredAgentRecord, "mealplanner-assistant")
        assert agent is not None and agent.capabilities["submit_candidates"] is False
        assert await session.get(ProfileSchemaRecord, "mealplanner-preferences-v1") is None
    await database.dispose()


@pytest.mark.asyncio
async def test_owner_can_approve_only_some_requested_attributes(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'partial-approval.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused", auth_enabled=False, google_id_token_audience=None
        ),
        database=database,
        store=MockMemoryStore(),
    )
    request = {
        "requestingAgentId": "grocery-agent",
        "requestingTeam": "grocery-platform",
        "targetSchemaId": "customer-preferences-v1",
        "requestedPermission": "READ",
        "attributes": ["customer.fulfillment_preference"],
        "businessReason": "Partial approval check",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/v1/admin/access-requests", headers=PLATFORM, json=request)
        assert created.status_code == 201, created.text
        request_id = created.json()["data"]["id"]
        path = f"/api/v1/admin/access-requests/{request_id}"

        not_requested = await client.post(
            f"{path}/approve", headers=PLATFORM, json={"attributes": ["customer.preferred_store"]}
        )
        assert not_requested.status_code == 400
        assert "not requested" in not_requested.text
        on_reject = await client.post(
            f"{path}/reject",
            headers=PLATFORM,
            json={"attributes": ["customer.fulfillment_preference"]},
        )
        assert on_reject.status_code == 400

        approved = await client.post(f"{path}/approve", headers=PLATFORM, json={})
        assert approved.status_code == 200, approved.text
        # Without a choice, everything requested is approved.
        assert approved.json()["data"]["approved_attributes"] == [
            "customer.fulfillment_preference"
        ]
    async with database.session() as session:
        grant = await session.get(AgentSchemaGrantRecord, "grocery-agent:customer-preferences-v1")
        assert grant is not None and grant.attributes == ["customer.fulfillment_preference"]
    await database.dispose()
