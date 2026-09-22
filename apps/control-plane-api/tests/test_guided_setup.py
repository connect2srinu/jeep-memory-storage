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
    ProfileSchemaRecord,
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
                "scope": {"userId": "alice", "domain": "familygrocery", "memberId": "alice"},
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
