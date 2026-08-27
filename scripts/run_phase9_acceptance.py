from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 9 governed-memory acceptance flow.")
    parser.add_argument("--control-plane-api-url", default=os.getenv("CONTROL_PLANE_API_URL", "http://localhost:8080"))
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "packages" / "test-fixtures" / "user-1001-acceptance.json",
    )
    return parser.parse_args()


def agent_headers(agent_id: str) -> dict[str, str]:
    token = os.getenv(f"{agent_id.replace('-', '_').upper()}_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {"X-Agent-ID": agent_id}


def admin_headers(role: str, domain: str) -> dict[str, str]:
    token = os.getenv("PHASE9_ADMIN_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {
        "X-Admin-User": f"phase9-{domain}-owner@example.com",
        "X-Admin-Roles": role,
        "X-Admin-Domains": domain,
    }


def checked(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.text}")
    return response.json()


def scope(fixture: dict[str, Any], domain: str) -> dict[str, str]:
    return {"userId": fixture["userId"], "appName": fixture["appName"], "domain": domain}


def seed_profiles(client: httpx.Client, fixture: dict[str, Any]) -> None:
    domain_agents = {
        "grocery": ("grocery-agent", "grocery-preferences-v1"),
        "customer": ("customer-agent", "customer-preferences-v1"),
        "inventory": ("inventory-agent", "inventory-preferences-v1"),
    }
    for domain, preferences in fixture["profiles"].items():
        agent_id, schema_id = domain_agents[domain]
        for attribute, value in preferences.items():
            checked(
                client.put(
                    f"/api/v1/runtime/preferences/{attribute}",
                    headers=agent_headers(agent_id),
                    json={"scope": scope(fixture, domain), "schemaId": schema_id, "value": value},
                )
            )


def approve_customer_access(client: httpx.Client) -> None:
    request = checked(
        client.post(
            "/api/v1/admin/access-requests",
            headers=admin_headers("AGENT_OWNER", "grocery"),
            json={
                "requestingAgentId": "grocery-agent",
                "requestingTeam": "grocery-platform",
                "targetSchemaId": "customer-preferences-v1",
                "requestedPermission": "READ",
                "businessReason": "Phase 9 preferred-store and fulfillment resolution",
            },
        )
    )["data"]
    checked(
        client.post(
            f"/api/v1/admin/access-requests/{request['id']}/approve",
            headers=admin_headers("SCHEMA_OWNER", "customer"),
            json={},
        )
    )


def resolve(client: httpx.Client, fixture: dict[str, Any]) -> dict[str, Any]:
    return checked(
        client.post(
            "/api/v1/runtime/preferences/resolve",
            headers=agent_headers("grocery-agent"),
            json={
                "scope": scope(fixture, "grocery"),
                "sessionId": fixture["sessionId"],
                "includeProvenance": True,
                "agentId": "grocery-agent",
            },
        )
    )


def assert_expected(snapshot: dict[str, Any], expected: dict[str, Any]) -> None:
    preferences = snapshot["preferences"]
    for key in ("preferred_store", "dietary_preference", "fulfillment_preference"):
        assert preferences[key]["value"] == expected[key]
    assert preferences["preferred_store"]["ownerDomain"] == expected["preferred_store_owner"]
    assert preferences["preferred_store"]["resolutionReason"] == expected["preferred_store_reason"]
    assert preferences["preferred_store"]["provenance"]["schema_id"] == (
        "customer-preferences-v1"
    )


def main() -> None:
    args = parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.control_plane_api_url, timeout=60.0) as client:
        seed_profiles(client, fixture)
        approve_customer_access(client)
        initial = resolve(client, fixture)
        assert_expected(initial, fixture["expected"])
        update = fixture["update"]
        mutation = checked(
            client.put(
                f"/api/v1/runtime/preferences/{update['attribute']}",
                headers=agent_headers("grocery-agent"),
                json={
                    "scope": scope(fixture, "grocery"),
                    "schemaId": "grocery-preferences-v1",
                    "value": update["value"],
                },
            )
        )
        refreshed = checked(
            client.post(
                "/api/v1/runtime/preferences/refresh",
                headers=agent_headers("grocery-agent"),
                json={"scope": scope(fixture, "grocery"), "sessionId": fixture["sessionId"]},
            )
        )
    assert mutation["profileVersion"] >= 2
    assert refreshed["snapshotVersion"] != initial["snapshotVersion"]
    assert refreshed["preferences"][update["expectedLogicalKey"]]["value"] == update["value"]
    print(
        json.dumps(
            {
                "status": "passed",
                "initialSnapshotVersion": initial["snapshotVersion"],
                "refreshedSnapshotVersion": refreshed["snapshotVersion"],
                "policyVersion": refreshed["policyVersion"],
                "schemaVersions": refreshed["schemaVersions"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
