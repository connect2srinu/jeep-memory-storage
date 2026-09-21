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
from control_plane_api.persistence.models import (
    AccessRequestRecord,
    AgentSchemaGrantRecord,
    AuditEventRecord,
)
from db_seed import seed_control_plane
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
        ControlPlaneApiSettings(
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
async def test_org_budget_project_health_and_runtime_governance(admin_environment) -> None:
    client, _ = admin_environment

    settings = await client.put(
        "/api/v1/admin/organizations/retail/settings",
        headers=PLATFORM,
        json={
            "budgetEnabled": True,
            "budgetAmount": 25000,
            "currency": "USD",
            "budgetPeriod": "MONTHLY",
            "thresholds": [{"percent": 80, "basis": "ACTUAL"}],
            "emailRecipients": ["finops@example.com"],
            "billingProjectIds": ["retail-agents-dev"],
        },
    )
    assert settings.status_code == 200
    assert settings.json()["data"]["sync_status"] == "PENDING_SYNC"

    project_settings = await client.put(
        "/api/v1/admin/projects/customer-experience/settings",
        headers=PLATFORM,
        json={
            "healthRefreshSeconds": 120,
            "latencyWarningMs": 1500,
            "errorRateWarning": 0.03,
            "notificationsEnabled": True,
            "notificationChannelIds": ["projects/test/notificationChannels/1"],
        },
    )
    assert project_settings.status_code == 200
    assert project_settings.json()["data"]["health_refresh_seconds"] == 120

    binding = await client.put(
        "/api/v1/admin/agents/customer-agent/runtime-binding",
        headers=PLATFORM,
        json={
            "provider": "ADK_LOCAL",
            "endpointUrl": "http://127.0.0.1:9",
            "environment": "development",
        },
    )
    assert binding.status_code == 200

    health = await client.get("/api/v1/admin/projects/customer-experience/health", headers=PLATFORM)
    assert health.status_code == 200
    customer = next(
        item for item in health.json()["data"]["agents"] if item["agent"]["id"] == "customer-agent"
    )
    assert customer["resource_tags"] == {
        "organization_id": "retail",
        "project_id": "customer-experience",
        "agent_id": "customer-agent",
        "environment": "development",
    }

    approvals = await client.get("/api/v1/admin/organizations/retail/approvals", headers=PLATFORM)
    assert approvals.status_code == 200
    assert set(approvals.json()["data"]) == {"incoming", "outgoing", "history"}


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
    assert created_organization.json()["data"]["status"] == "ACTIVE"
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
async def test_organization_catalog_marks_foreign_schemas_restricted(admin_environment) -> None:
    client, _ = admin_environment
    await client.post(
        "/api/v1/admin/organizations",
        headers=PLATFORM,
        json={"id": "healthcare", "name": "Healthcare"},
    )
    response = await client.get("/api/v1/admin/schemas?organizationId=healthcare", headers=VIEWER)
    assert response.status_code == 200
    grocery = next(
        item for item in response.json()["items"] if item["id"] == "grocery-preferences-v1"
    )
    assert grocery["visibility"] == "RESTRICTED"
    assert grocery["editable"] is False
    assert grocery["access_status"] == "NOT_REQUESTED"


@pytest.mark.asyncio
async def test_schema_edit_creates_draft_and_approval_switches_active_version(
    admin_environment,
) -> None:
    client, _ = admin_environment
    current = await client.get("/api/v1/admin/schemas/grocery-preferences-v1", headers=PLATFORM)
    active = next(item for item in current.json()["data"]["versions"] if item["status"] == "ACTIVE")
    request = await client.post(
        "/api/v1/admin/schemas/grocery-preferences-v1/versions",
        headers=PLATFORM,
        json={
            "version": "2.0",
            "scopeDefinitionId": active["scope_definition_id"],
            "vertexSchemaDefinition": active["vertex_schema_definition"],
            "generationConfig": active["generation_config"],
            "mappings": [
                {
                    "attributeId": item["attribute_id"],
                    "profileField": item["profile_field"],
                }
                for item in active["mappings"]
            ],
        },
    )
    assert request.status_code == 202, request.text
    request_id = request.json()["data"]["id"]
    draft = await client.get("/api/v1/admin/schemas/grocery-preferences-v1", headers=PLATFORM)
    assert any(
        item["version"] == "2.0" and item["status"] == "DRAFT"
        for item in draft.json()["data"]["versions"]
    )

    approved = await client.post(
        f"/api/v1/admin/resource-change-requests/{request_id}/approve",
        headers=PLATFORM,
        json={"reason": "Validated by schema owner"},
    )
    assert approved.status_code == 200, approved.text
    published = await client.get("/api/v1/admin/schemas/grocery-preferences-v1", headers=PLATFORM)
    versions = published.json()["data"]["versions"]
    assert any(item["version"] == "2.0" and item["status"] == "ACTIVE" for item in versions)
    assert any(
        item["version"] == active["version"] and item["status"] == "DEPRECATED" for item in versions
    )

    active_v2 = next(item for item in versions if item["status"] == "ACTIVE")
    assert len(active_v2["mappings"]) > 1
    destructive = await client.post(
        "/api/v1/admin/schemas/grocery-preferences-v1/versions",
        headers=PLATFORM,
        json={
            "version": "3.0",
            "scopeDefinitionId": active_v2["scope_definition_id"],
            "vertexSchemaDefinition": active_v2["vertex_schema_definition"],
            "mappings": [
                {
                    "attributeId": item["attribute_id"],
                    "profileField": item["profile_field"],
                }
                for item in active_v2["mappings"][1:]
            ],
        },
    )
    assert destructive.status_code == 409
    assert "cannot be removed or renamed" in destructive.json()["message"]


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
async def test_domain_edits_remain_inactive_until_approved(admin_environment) -> None:
    client, _ = admin_environment
    original = await client.get("/api/v1/admin/domains/grocery", headers=VIEWER)
    original_description = original.json()["data"]["description"]

    requested = await client.patch(
        "/api/v1/admin/domains/grocery",
        headers=PLATFORM,
        json={"changes": {"description": "Approved grocery domain description"}},
    )
    assert requested.status_code == 200, requested.text
    request = requested.json()["data"]
    assert request["status"] == "PENDING"
    assert request["proposed_changes"] == {"description": "Approved grocery domain description"}

    unchanged = await client.get("/api/v1/admin/domains/grocery", headers=VIEWER)
    assert unchanged.json()["data"]["description"] == original_description

    duplicate = await client.patch(
        "/api/v1/admin/domains/grocery",
        headers=PLATFORM,
        json={"changes": {"description": "A second pending description"}},
    )
    assert duplicate.status_code == 409

    listed = await client.get("/api/v1/admin/resource-change-requests", headers=VIEWER)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == request["id"]

    approved = await client.post(
        f"/api/v1/admin/resource-change-requests/{request['id']}/approve",
        headers=PLATFORM,
        json={"reason": "Reviewed by platform governance"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "APPROVED"

    published = await client.get("/api/v1/admin/domains/grocery", headers=VIEWER)
    assert published.json()["data"]["description"] == ("Approved grocery domain description")


@pytest.mark.asyncio
async def test_agent_schema_access_catalog_tracks_request_and_approval(
    admin_environment,
) -> None:
    client, _ = admin_environment
    initial = await client.get(
        "/api/v1/admin/agents/customer-agent/schema-access", headers=PLATFORM
    )
    assert initial.status_code == 200
    inventory = next(
        item for item in initial.json()["items"] if item["id"] == "inventory-preferences-v1"
    )
    assert inventory["access_status"] == "NOT_REQUESTED"
    assert inventory["requestable"] is True

    requested = await client.post(
        "/api/v1/admin/access-requests",
        headers=PLATFORM,
        json={
            "requestingAgentId": "customer-agent",
            "requestingTeam": "customer-platform",
            "targetSchemaId": "inventory-preferences-v1",
            "requestedPermission": "READ",
            "businessReason": "Use availability in the customer experience",
        },
    )
    assert requested.status_code == 201, requested.text
    request_id = requested.json()["data"]["id"]
    pending = await client.get(
        "/api/v1/admin/agents/customer-agent/schema-access", headers=PLATFORM
    )
    inventory = next(
        item for item in pending.json()["items"] if item["id"] == "inventory-preferences-v1"
    )
    assert inventory["access_status"] == "PENDING"
    assert inventory["requestable"] is False

    approved = await client.post(
        f"/api/v1/admin/access-requests/{request_id}/approve",
        headers=INVENTORY_SCHEMA_OWNER,
        json={"reason": "Approved for read-only availability"},
    )
    assert approved.status_code == 200, approved.text
    active = await client.get("/api/v1/admin/agents/customer-agent/schema-access", headers=PLATFORM)
    inventory = next(
        item for item in active.json()["items"] if item["id"] == "inventory-preferences-v1"
    )
    assert inventory["access_status"] == "APPROVED"
    assert inventory["permission"] == "READ"


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
        ControlPlaneApiSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            auth_enabled=False,
            google_id_token_audience=None,
        )
    )
    schema = app.openapi()
    paths = schema["paths"]
    expected = {
        "/api/v1/admin/domains",
        "/api/v1/admin/domains/{resource_id}/detail",
        "/api/v1/admin/scopes",
        "/api/v1/admin/schemas",
        "/api/v1/admin/schemas/{resource_id}/agents",
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


def test_openapi_documents_planes_tags_and_summaries() -> None:
    app = create_app(
        ControlPlaneApiSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            auth_enabled=False,
            google_id_token_audience=None,
        )
    )
    schema = app.openapi()
    info = schema["info"]
    assert "Control Plane API" in info["description"]
    assert "/docs" in info["description"]
    tag_names = {tag["name"] for tag in schema.get("tags", [])}
    assert {"admin", "runtime"} <= tag_names
    # Operation-level summaries surface on the new aggregation endpoints.
    detail = schema["paths"]["/api/v1/admin/domains/{resource_id}/detail"]["get"]
    assert detail["summary"] == "Aggregate domain detail"
    assert detail["tags"] == ["admin"]
    agents = schema["paths"]["/api/v1/admin/schemas/{resource_id}/agents"]["get"]
    assert agents["summary"] == "Agents with access to a schema"
    # Operational endpoints stay out of the public schema.
    assert "/healthz" not in schema["paths"]
    assert "/internal/metrics" not in schema["paths"]


@pytest.mark.asyncio
async def test_domain_detail_aggregates_children(admin_environment) -> None:
    client, _ = admin_environment
    response = await client.get("/api/v1/admin/domains/grocery/detail", headers=VIEWER)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["domain"]["id"] == "grocery"
    assert data["organization"]["id"] == "retail"
    assert data["project"]["id"] == "shopping"

    # A domain owns its scope(s); grocery has the member and household scopes in the seed.
    assert [scope["id"] for scope in data["scopes"]] == [
        "grocery:household-member-scope",
        "grocery:household-scope",
        "grocery:profile-scope",
    ]

    schema = next(item for item in data["schemas"] if item["id"] == "grocery-preferences-v1")
    assert schema["versions"][0]["mappings"], "schema version exposes preference mappings"
    assert "access_status" in schema
    # grocery-agent, grocery-readonly-agent, delivery-agent, store-agent hold active grants.
    assert schema["active_grant_count"] >= 3

    home_agent_ids = {agent["id"] for agent in data["home_agents"]}
    assert {"grocery-agent", "grocery-readonly-agent"} <= home_agent_ids

    # Resolution is a domain-level default here (no agent-specific policy seeded).
    assert data["resolution"]["domain_default"]["id"] == "grocery:test-policy:1"

    assert set(data["pending_requests"]) == {"access", "changes"}
    assert isinstance(data["audit"], list)

    missing = await client.get("/api/v1/admin/domains/not-a-domain/detail", headers=VIEWER)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_schema_agent_access_distinguishes_project_and_grant(admin_environment) -> None:
    client, _ = admin_environment
    response = await client.get(
        "/api/v1/admin/schemas/grocery-preferences-v1/agents", headers=VIEWER
    )
    assert response.status_code == 200
    by_agent = {item["agent_id"]: item for item in response.json()["items"]}

    # Owning-project agent with an explicit grant.
    grocery = by_agent["grocery-agent"]
    assert grocery["same_project"] is True
    assert grocery["access_kind"] == "OWNING_PROJECT_GRANT"
    assert grocery["permission"] == "READ_WRITE"

    # Same project, no grant: explicit-only model means eligible, not granted.
    inventory = by_agent["inventory-agent"]
    assert inventory["same_project"] is True
    assert inventory["access_kind"] == "ELIGIBLE_NOT_GRANTED"
    assert inventory["permission"] is None

    # Different project, no grant.
    customer = by_agent["customer-agent"]
    assert customer["same_project"] is False
    assert customer["access_kind"] == "NONE"

    # A cross-project grant is labelled distinctly on the customer schema.
    customer_schema = await client.get(
        "/api/v1/admin/schemas/customer-preferences-v1/agents", headers=VIEWER
    )
    cross = {item["agent_id"]: item for item in customer_schema.json()["items"]}["grocery-agent"]
    assert cross["same_project"] is False
    assert cross["access_kind"] == "CROSS_PROJECT_GRANT"
    assert cross["permission"] == "READ"
