from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from db_seed import seed_control_plane
from memory_api.application import create_app
from memory_api.config import MemoryApiSettings
from memory_api.integrations import MockMemoryStore
from memory_api.persistence import Database
from memory_api.persistence.models import (
    AccessRequestRecord,
    AgentSchemaGrantRecord,
    AuditEventRecord,
)
from sqlalchemy import func, select

PLATFORM = {"X-Admin-User": "platform@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}
GROCERY_AGENT_OWNER = {
    "X-Admin-User": "grocery-agent-owner@example.com",
    "X-Admin-Roles": "AGENT_OWNER",
    "X-Admin-Domains": "grocery",
}
CUSTOMER_SCHEMA_OWNER = {
    "X-Admin-User": "customer-schema-owner@example.com",
    "X-Admin-Roles": "SCHEMA_OWNER",
    "X-Admin-Domains": "customer",
}
INVENTORY_SCHEMA_OWNER = {
    "X-Admin-User": "inventory-schema-owner@example.com",
    "X-Admin-Roles": "SCHEMA_OWNER",
    "X-Admin-Domains": "inventory",
}
VIEWER = {"X-Admin-User": "viewer@example.com", "X-Admin-Roles": "VIEWER"}


@pytest_asyncio.fixture
async def admin_environment(tmp_path: Path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        MemoryApiSettings(
            database_url="unused",
            auth_enabled=False,
            google_id_token_audience=None,
        ),
        database=database,
        store=MockMemoryStore(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, database
    await database.dispose()


@pytest.mark.asyncio
async def test_admin_authentication_and_viewer_read_only(admin_environment) -> None:
    client, _ = admin_environment
    missing = await client.get("/api/v1/admin/domains")
    assert missing.status_code == 401
    assert missing.json()["code"] == "UNAUTHENTICATED"

    listed = await client.get("/api/v1/admin/domains", headers=VIEWER)
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()["items"]} >= {"customer", "grocery"}

    denied = await client.post(
        "/api/v1/admin/domains",
        headers=VIEWER,
        json={
            "id": "rewards",
            "organizationId": "retail",
            "projectId": "shopping",
            "name": "Rewards",
            "ownerTeam": "rewards-team",
        },
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_organization_project_hierarchy_is_enforced(admin_environment) -> None:
    client, _ = admin_environment
    organizations = await client.get("/api/v1/admin/organizations", headers=VIEWER)
    projects = await client.get("/api/v1/admin/projects", headers=VIEWER)
    assert {item["id"] for item in organizations.json()["items"]} == {"retail"}
    assert {item["id"] for item in projects.json()["items"]} >= {
        "shopping",
        "customer-experience",
    }

    created_organization = await client.post(
        "/api/v1/admin/organizations",
        headers=PLATFORM,
        json={"id": "healthcare", "name": "Healthcare"},
    )
    assert created_organization.status_code == 201
    created_project = await client.post(
        "/api/v1/admin/projects",
        headers=PLATFORM,
        json={
            "id": "patient-experience",
            "organizationId": "healthcare",
            "name": "Patient Experience",
            "ownerTeam": "patient-platform",
        },
    )
    assert created_project.status_code == 201

    project_member_without_organization = await client.post(
        "/api/v1/admin/projects/patient-experience/members",
        headers=PLATFORM,
        json={
            "memberPrincipal": "patient-owner@example.com",
            "displayName": "Patient Owner",
            "role": "OWNER",
        },
    )
    assert project_member_without_organization.status_code == 409

    organization_member = await client.post(
        "/api/v1/admin/organizations/healthcare/members",
        headers=PLATFORM,
        json={
            "memberPrincipal": "Patient-Owner@Example.com",
            "displayName": "Patient Owner",
            "role": "OWNER",
        },
    )
    assert organization_member.status_code == 201
    assert organization_member.json()["data"]["member_principal"] == ("patient-owner@example.com")
    project_member = await client.post(
        "/api/v1/admin/projects/patient-experience/members",
        headers=PLATFORM,
        json={
            "memberPrincipal": "patient-owner@example.com",
            "displayName": "Patient Owner",
            "role": "ADMIN",
        },
    )
    assert project_member.status_code == 201

    hierarchy = await client.get("/api/v1/admin/organization-hierarchy", headers=VIEWER)
    assert hierarchy.status_code == 200
    healthcare = next(
        item for item in hierarchy.json()["data"]["organizations"] if item["id"] == "healthcare"
    )
    assert healthcare["members"][0]["role"] == "OWNER"
    assert healthcare["projects"][0]["members"][0]["role"] == "ADMIN"

    mismatched = await client.post(
        "/api/v1/admin/domains",
        headers=PLATFORM,
        json={
            "id": "invalid-domain",
            "organizationId": "retail",
            "projectId": "patient-experience",
            "name": "Invalid Domain",
            "ownerTeam": "invalid-team",
        },
    )
    assert mismatched.status_code == 409
    assert "does not belong" in mismatched.json()["message"]


@pytest.mark.asyncio
async def test_control_plane_resource_crud_and_lifecycle(admin_environment) -> None:
    client, _ = admin_environment
    created_domain = await client.post(
        "/api/v1/admin/domains",
        headers=PLATFORM,
        json={
            "id": "rewards",
            "organizationId": "retail",
            "projectId": "shopping",
            "name": "Rewards",
            "description": "Rewards preferences",
            "ownerTeam": "rewards-team",
        },
    )
    assert created_domain.status_code == 201, created_domain.text
    assert created_domain.json()["data"]["status"] == "DRAFT"

    resources = [
        (
            "scopes",
            {
                "id": "rewards:profile-scope",
                "scopeType": "DOMAIN_PROFILE",
                "scopeKeys": ["user_id", "app_name"],
                "ownerDomainId": "rewards",
            },
        ),
        (
            "schemas",
            {
                "id": "rewards-preferences-v1",
                "domainId": "rewards",
                "displayName": "Rewards Preferences",
                "ownerTeam": "rewards-team",
                "version": "1",
                "scopeDefinitionId": "rewards:profile-scope",
                "vertexSchemaDefinition": {
                    "type": "object",
                    "properties": {"preferred_reward": {"type": "string"}},
                },
                "mappings": [
                    {
                        "attributeId": "rewards.preferred_reward",
                        "profileField": "preferred_reward",
                    }
                ],
            },
        ),
        (
            "agents",
            {
                "id": "rewards-agent",
                "displayName": "Rewards Agent",
                "organizationId": "retail",
                "projectId": "shopping",
                "domainId": "rewards",
                "runtimeType": "ADK_CLOUD_RUN",
                "identityType": "GOOGLE_SERVICE_ACCOUNT",
                "capabilities": {"resolve_context": True},
            },
        ),
        (
            "resolution-policies",
            {
                "id": "rewards-policy-v1",
                "agentId": "rewards-agent",
                "name": "Rewards policy",
                "version": "1",
                "defaultRules": {"strategy": "DOMAIN_AUTHORITY"},
                "schemaPriorities": [{"schemaId": "rewards-preferences-v1", "priority": 0}],
                "attributeOverrides": [
                    {
                        "attributeId": "rewards.preferred_reward",
                        "schemaPrecedence": ["rewards-preferences-v1"],
                        "rules": {"minimum_confidence": 0.8},
                    }
                ],
            },
        ),
        (
            "dynamic-memory-policies",
            {
                "id": "rewards-dynamic-v1",
                "level": "DOMAIN",
                "domainId": "rewards",
                "confidenceThreshold": 0.8,
            },
        ),
    ]
    preference = await client.post(
        "/api/v1/admin/preference-catalog",
        headers=PLATFORM,
        json={
            "attributeId": "rewards.preferred_reward",
            "displayName": "Preferred Reward",
            "description": "Reward selection",
            "dataType": "string",
            "sensitivityClassification": "normal",
            "canonicalOwnerId": "rewards",
        },
    )
    assert preference.status_code == 201, preference.text
    for resource, payload in resources:
        response = await client.post(f"/api/v1/admin/{resource}", headers=PLATFORM, json=payload)
        assert response.status_code == 201, (resource, response.text)

    fetched = await client.get("/api/v1/admin/agents/rewards-agent", headers=VIEWER)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["domain_id"] == "rewards"

    schema = await client.get("/api/v1/admin/schemas/rewards-preferences-v1", headers=VIEWER)
    assert schema.json()["data"]["versions"][0]["mappings"][0]["attribute_id"] == (
        "rewards.preferred_reward"
    )
    policy = await client.get("/api/v1/admin/resolution-policies/rewards-policy-v1", headers=VIEWER)
    assert policy.json()["data"]["schema_priorities"][0]["schema_id"] == ("rewards-preferences-v1")

    schema_pending = await client.patch(
        "/api/v1/admin/schemas/rewards-preferences-v1",
        headers=PLATFORM,
        json={"status": "PENDING_APPROVAL"},
    )
    assert schema_pending.status_code == 200
    assert schema_pending.json()["data"]["versions"][0]["status"] == "PENDING_APPROVAL"

    policy_updated = await client.patch(
        "/api/v1/admin/resolution-policies/rewards-policy-v1",
        headers=PLATFORM,
        json={
            "changes": {
                "defaultRules": {"strategy": "CONFIDENCE_THEN_PRIORITY"},
                "schemaPriorities": [{"schemaId": "rewards-preferences-v1", "priority": 2}],
                "attributeOverrides": [
                    {
                        "attributeId": "rewards.preferred_reward",
                        "schemaPrecedence": ["rewards-preferences-v1"],
                        "rules": {"minimum_confidence": 0.9},
                    }
                ],
            }
        },
    )
    assert policy_updated.status_code == 200, policy_updated.text
    assert policy_updated.json()["data"]["schema_priorities"][0]["priority"] == 2
    assert policy_updated.json()["data"]["attribute_overrides"][0]["rules"] == {
        "minimum_confidence": 0.9
    }

    pending = await client.patch(
        "/api/v1/admin/agents/rewards-agent",
        headers=PLATFORM,
        json={"status": "PENDING_APPROVAL", "changes": {"display_name": "Rewards Agent"}},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["data"]["status"] == "PENDING_APPROVAL"
    assert pending.json()["data"]["display_name"] == "Rewards Agent"

    invalid = await client.patch(
        "/api/v1/admin/agents/rewards-agent",
        headers=PLATFORM,
        json={"status": "ACTIVE"},
    )
    assert invalid.status_code == 409

    duplicate = await client.post(
        "/api/v1/admin/domains",
        headers=PLATFORM,
        json={
            "id": "rewards",
            "organizationId": "retail",
            "projectId": "shopping",
            "name": "Duplicate",
            "ownerTeam": "team",
        },
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_access_approval_grant_revoke_and_transactional_audit(admin_environment) -> None:
    client, database = admin_environment
    requested = await client.post(
        "/api/v1/admin/access-requests",
        headers=GROCERY_AGENT_OWNER,
        json={
            "requestingAgentId": "grocery-agent",
            "requestingTeam": "grocery-platform",
            "targetSchemaId": "customer-preferences-v1",
            "requestedPermission": "READ",
            "businessReason": "Use customer fulfillment preferences",
            "expiration": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
    )
    assert requested.status_code == 201, requested.text
    request_id = requested.json()["data"]["id"]

    wrong_owner = await client.post(
        f"/api/v1/admin/access-requests/{request_id}/approve",
        headers=INVENTORY_SCHEMA_OWNER,
        json={},
    )
    assert wrong_owner.status_code == 403

    approved = await client.post(
        f"/api/v1/admin/access-requests/{request_id}/approve",
        headers=CUSTOMER_SCHEMA_OWNER,
        json={},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "APPROVED"

    async with database.session() as session:
        grant = await session.get(AgentSchemaGrantRecord, "grocery-agent:customer-preferences-v1")
        assert grant is not None
        assert grant.permission == "READ"
        assert grant.status == "ACTIVE"
        audits_after_approval = await session.scalar(
            select(func.count()).select_from(AuditEventRecord)
        )

    revoked = await client.post(
        f"/api/v1/admin/access-requests/{request_id}/revoke",
        headers=CUSTOMER_SCHEMA_OWNER,
        json={"reason": "Business use ended"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "REVOKED"

    async with database.session() as session:
        grant = await session.get(AgentSchemaGrantRecord, "grocery-agent:customer-preferences-v1")
        request = await session.get(AccessRequestRecord, request_id)
        audits_after_revoke = await session.scalar(
            select(func.count()).select_from(AuditEventRecord)
        )
        assert grant is not None and grant.status == "REVOKED"
        assert request is not None and request.status == "REVOKED"
        assert audits_after_revoke == audits_after_approval + 2


@pytest.mark.asyncio
async def test_access_rejection_and_expiry_disable_runtime_grant(admin_environment) -> None:
    client, database = admin_environment
    rejected_request = await client.post(
        "/api/v1/admin/access-requests",
        headers=GROCERY_AGENT_OWNER,
        json={
            "requestingAgentId": "grocery-readonly-agent",
            "requestingTeam": "grocery-platform",
            "targetSchemaId": "customer-preferences-v1",
            "requestedPermission": "READ",
            "businessReason": "Rejected request",
        },
    )
    assert rejected_request.status_code == 201
    rejected_id = rejected_request.json()["data"]["id"]
    rejected = await client.post(
        f"/api/v1/admin/access-requests/{rejected_id}/reject",
        headers=CUSTOMER_SCHEMA_OWNER,
        json={"reason": "Insufficient justification"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"

    expiration = datetime.now(UTC) + timedelta(minutes=5)
    requested = await client.post(
        "/api/v1/admin/access-requests",
        headers=GROCERY_AGENT_OWNER,
        json={
            "requestingAgentId": "grocery-agent",
            "requestingTeam": "grocery-platform",
            "targetSchemaId": "customer-preferences-v1",
            "requestedPermission": "READ",
            "businessReason": "Short-lived access",
            "expiration": expiration.isoformat(),
        },
    )
    request_id = requested.json()["data"]["id"]
    approved = await client.post(
        f"/api/v1/admin/access-requests/{request_id}/approve",
        headers=CUSTOMER_SCHEMA_OWNER,
        json={},
    )
    assert approved.status_code == 200

    past = datetime.now(UTC) - timedelta(minutes=1)
    async with database.session() as session:
        access_request = await session.get(AccessRequestRecord, request_id)
        grant = await session.get(AgentSchemaGrantRecord, "grocery-agent:customer-preferences-v1")
        assert access_request is not None and grant is not None
        access_request.expiration = past
        grant.expires_at = past

    expired = await client.post(
        f"/api/v1/admin/access-requests/{request_id}/expire",
        headers=CUSTOMER_SCHEMA_OWNER,
        json={"reason": "Scheduled expiry"},
    )
    assert expired.status_code == 200, expired.text
    assert expired.json()["data"]["status"] == "EXPIRED"
    async with database.session() as session:
        grant = await session.get(AgentSchemaGrantRecord, "grocery-agent:customer-preferences-v1")
        assert grant is not None and grant.status == "EXPIRED"


def test_openapi_exposes_versioned_admin_resources() -> None:
    app = create_app(
        MemoryApiSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            auth_enabled=False,
            google_id_token_audience=None,
        )
    )
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/admin/domains",
        "/api/v1/admin/scopes",
        "/api/v1/admin/schemas",
        "/api/v1/admin/preference-catalog",
        "/api/v1/admin/agents",
        "/api/v1/admin/access-requests",
        "/api/v1/admin/resolution-policies",
        "/api/v1/admin/dynamic-memory-policies",
        "/api/v1/admin/audit",
        "/api/v1/admin/memory-setups/preview",
        "/api/v1/admin/memory-setups/activate",
    }
    assert expected <= set(paths)
