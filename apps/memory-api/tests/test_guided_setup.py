from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from db_seed import seed_control_plane
from memory_api.application import create_app
from memory_api.config import MemoryApiSettings
from memory_api.integrations import MockMemoryStore
from memory_api.persistence import Database
from memory_api.persistence.models import (
    AccessRequestRecord,
    AgentSchemaGrantRecord,
    ProfileSchemaRecord,
    RegisteredAgentRecord,
    ScopeDefinitionRecord,
)
from sqlalchemy import select

PLATFORM = {"X-Admin-User": "platform@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}


def setup_payload() -> dict[str, object]:
    return {
        "useCase": {
            "name": "Rewards Personalization",
            "description": "Remember reward choices",
            "owningTeam": "rewards-platform",
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
        MemoryApiSettings(
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
