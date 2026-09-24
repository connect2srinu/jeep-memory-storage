#!/usr/bin/env python3
"""Privacy and legal controls demo against the Control Plane runtime and admin APIs.

Walks through each privacy risk and shows the platform control that prevents it: health-data consent,
other adults' health data, restricted content, inferred protected-class facts, wrong-person
attribution, household isolation, retention, and deletion with consent withdrawal.

Assumes the local stack is up (API on :8080) and a Household + members setup whose agent has
READ_WRITE on a household schema with `excluded_products` and a per-member schema with `dislikes`
and a health attribute `allergies` (the setup in docs/dynamic-household-test-guide.md). Each run uses
a new throwaway customer and forgets its memories at the end. Nothing here needs an LLM.

Usage:  python3 scripts/privacy_controls_demo.py [--base http://localhost:8080]
            [--agent familygrocery-assistant] [--domain familygrocery] [--org retail]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

ARGS = argparse.ArgumentParser(description=__doc__)
ARGS.add_argument("--base", default="http://localhost:8080")
ARGS.add_argument("--agent", default="familygrocery-assistant")
ARGS.add_argument("--domain", default="familygrocery")
ARGS.add_argument("--org", default="retail")
ARGS.add_argument("--project", default="shopping")
ARGS.add_argument(
    "--with-purpose-check",
    action="store_true",
    help="also register a demo agent 'privacy-demo-ads' with purpose advertising (kept afterwards)",
)
OPTS = ARGS.parse_args()

RUN = int(time.time())
CUSTOMER = f"privacy-demo-{RUN}"
NEIGHBOR = f"privacy-demo-{RUN}-neighbor"
ADMIN = {"X-Admin-User": "privacy-demo@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}
PASSED = 0
FAILED = 0


def call(method: str, path: str, body: dict | None = None, admin: bool = False) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    headers.update(ADMIN if admin else {"X-Agent-ID": OPTS.agent})
    request = urllib.request.Request(
        OPTS.base + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.getcode(), json.loads(response.read() or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def call_settled(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """Admin call that retries briefly on 404: the API commits after it responds, so a record
    created by the previous call may not be visible for a moment."""
    for _ in range(10):
        code, result = call(method, path, body, admin=True)
        if code != 404:
            break
        time.sleep(0.3)
    return code, result


def scope(user: str = CUSTOMER, **extra: str) -> dict:
    return {"userId": user, "domain": OPTS.domain, **extra}


def save(attribute: str, value: str, member_id: str | None = None, **body) -> tuple[int, dict]:
    extra = {"memberId": member_id} if member_id else {}
    return call(
        "PUT",
        f"/api/v1/runtime/preferences/{OPTS.domain}.{attribute}",
        {"scope": scope(**extra), "value": value, **body},
    )


def resolve(user: str = CUSTOMER, member_id: str | None = None, **extra: str) -> tuple[int, dict]:
    keys = {"memberId": member_id} if member_id else {}
    return call(
        "POST",
        "/api/v1/runtime/preferences/resolve",
        {"scope": scope(user, **keys, **extra), "sessionId": f"demo-{RUN}"},
    )


def add_member(name: str, relationship: str) -> str:
    _, body = call(
        "POST",
        "/api/v1/runtime/household/members",
        {"scope": scope(), "name": name, "relationship": relationship, "confirmed": True},
    )
    return body.get("memberId", "")


def consents(household_id: str) -> list[dict]:
    path = f"/api/v1/admin/organizations/{OPTS.org}/households/{household_id}/consents"
    return call("GET", path, admin=True)[1].get("items", [])


def check(label: str, ok: bool, detail: object = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}  -- {detail}")


def show(label: str, text: object) -> None:
    print(f"        {label}: {text}")


print(f"# Privacy controls demo  (customer={CUSTOMER}, agent={OPTS.agent}, org={OPTS.org})\n")

code, snapshot = resolve()
household = snapshot.get("householdId", "")
check("first use creates the customer's household (surrogate id)", code == 200 and household.startswith("hh_"),
      snapshot)

print("\n## 1 · Health data about a child needs confirmation and records consent  (WA MHMDA, CCPA)")
code, asked = save("allergies", "peanuts", memberName="Ryan", relationship="son")
check("first call saves nothing and asks", asked.get("status") == "needs_confirmation", asked)
show("platform question", asked.get("confirmationPrompt"))
ryan = asked.get("memberId", "")
check("nothing stored before the customer says yes",
      "allergies" not in resolve(member_id=ryan)[1].get("preferences", {}))
code, forged = save("allergies", "shellfish", ryan, confirmed=True)
check("agent can't self-confirm a value the customer wasn't asked about",
      forged.get("status") == "needs_confirmation", forged)
code, saved = save("allergies", "peanuts", ryan, confirmed=True)
check("customer's yes saves the allergy", saved.get("status") == "updated", saved)
granted = [c for c in consents(household) if c.get("status") == "GRANTED"]
check("consent ledger records who, about whom, and the exact wording", len(granted) == 1, granted)
if granted:
    show("consent", {k: granted[0].get(k) for k in ("category", "attribute_id", "prompt_text", "status")})

print("\n## 2 · Another adult's health data is refused  (consent must come from that adult)")
code, refused = save("allergies", "shellfish", memberName="Meera", relationship="wife")
check("health data about a spouse is not stored against her", refused.get("status") == "not_allowed", refused)
show("platform message", refused.get("message"))
names = [m.get("displayName") for m in resolve()[1].get("householdMembers", [])]
check("the spouse isn't even added to the household", "Meera" not in names, names)
code, product_filter = save("excluded_products", "shellfish")
check("option (b): an unattributed household product filter is allowed",
      product_filter.get("status") == "updated", product_filter)

print("\n## 3 · Restricted content is never stored, even when the customer asks")
for label, value in (
    ("Social Security number", "my SSN is 123-45-6789"),
    ("weapons", "wishes he could bring his guns into the store"),
    ("discriminatory instruction", "don't let a certain person pick my order"),
):
    code, body = save("dislikes", value)
    check(f"{label} -> 400", code == 400, body)
show("example message", body.get("message"))

print("\n## 4 · Inferred protected-class facts are rejected; the actionable form is kept")
code, body = save("dislikes", "pork - user is Muslim", source="inference")
check("inferred religion -> 403", code == 403, body)
code, body = save("dislikes", "user may be pregnant", source="inference")
check("inferred pregnancy -> 403", code == 403, body)
code, body = save("dislikes", "pork")
check("the actionable preference 'pork' is stored", code == 200 and body.get("status") == "updated", body)

print("\n## 5 · Wrong-person attribution is prevented  (accuracy, right to correct)")
code, body = save("allergies", "tree nuts", memberName="Ryann")
check("a misspelled name never auto-matches for health data", body.get("status") != "updated", body)
show("platform response", body.get("confirmationPrompt") or body.get("message"))
code, body = save("dislikes", "olives", memberName="Ryann")
check("for a normal preference the close variant matches Ryan", body.get("memberId") == ryan, body)
add_member("Sam", "son")
code, body = save("dislikes", "kale", memberName="Sam", relationship="daughter")
check("'Sam, my daughter' is not merged into Sam the son", body.get("status") == "needs_confirmation", body)
save("dislikes", "kale", body.get("memberId"), confirmed=True)
code, body = save("dislikes", "beets", memberName="Sam")
check("two Sams -> the customer is asked which one", body.get("status") == "ambiguous", body)
show("platform question", body.get("confirmationPrompt"))

print("\n## 6 · Customers can't reach another household")
neighbor_household = resolve(NEIGHBOR)[1].get("householdId", "")
code, body = resolve(householdId=neighbor_household)
check("naming another customer's household -> 403", code == 403, body)

print("\n## 7 · Retention limits  (CCPA/COPPA: no indefinite retention)")
sweep = f"/api/v1/admin/organizations/{OPTS.org}/retention/sweep"
later = (datetime.now(UTC) + timedelta(days=400)).isoformat()
code, body = call("POST", sweep, {"dryRun": True, "asOf": later}, admin=True)
data = body.get("data", {})
check("a preview 400 days ahead shows values that would expire", data.get("valuesMatched", 0) >= 1, body)
show("preview", {k: data.get(k) for k in ("valuesMatched", "provisionalMembers", "pendingConsents")})
code, body = call("POST", sweep, {"dryRun": False, "asOf": later}, admin=True)
check("a real sweep always runs as of now (no forward-dated deletion)", code == 400, body)

print("\n## 8 · Deletion and consent withdrawal  (right to delete)")
code, body = call(
    "POST",
    f"/api/v1/runtime/preferences/{OPTS.domain}.allergies/forget",
    {"scope": scope(memberId=ryan)},
)
check("forgetting the allergy deletes it", body.get("status") == "forgotten", body)
show("platform message", body.get("message"))
statuses = sorted(c.get("status") for c in consents(household))
check("its consent is marked WITHDRAWN", "WITHDRAWN" in statuses, statuses)
code, body = call("POST", "/api/v1/runtime/memory/forget", {"scope": scope(householdId=household)})
check("forgetting the household cascades to every member", code == 200, body)
call("POST", "/api/v1/runtime/memory/forget", {"scope": scope(NEIGHBOR)})
remaining = resolve(member_id=ryan)[1].get("preferences", {})
check("no stored values are left for Ryan", not remaining, remaining)
roster = [(m.get("displayName"), m.get("relationship")) for m in resolve()[1].get("householdMembers", [])]
show("KNOWN GAP - household roster kept after forget", roster)
show("KNOWN GAP - consent ledger kept (withdrawn)", sorted(c.get("status") for c in consents(household)))

if OPTS.with_purpose_check:
    print("\n## 9 · Advertising can't read per-person or health data  (CCPA under-16, COPPA)")
    ads = "privacy-demo-ads"
    code, body = call(
        "POST",
        "/api/v1/admin/agents",
        {
            "id": ads,
            "displayName": "Privacy demo ads agent",
            "organizationId": OPTS.org,
            "projectId": OPTS.project,
            "domainId": OPTS.domain,
            "runtimeType": "OTHER",
            "identityType": "LOCAL_POC",
            "capabilities": {"resolve_context": True},
            "purpose": "advertising",
        },
        admin=True,
    )
    check("an agent declaring purpose 'advertising' is registered", code in {201, 409}, body)
    schema = f"{OPTS.domain}-member-preferences-v1"
    code, body = call_settled(
        "POST",
        "/api/v1/admin/access-requests",
        {
            "requestingAgentId": ads,
            "requestingTeam": "marketing",
            "targetSchemaId": schema,
            "requestedPermission": "READ",
            "businessReason": "Targeted offers",
        },
    )
    request_id = body.get("data", {}).get("id")
    if request_id is None:  # a pending request from an earlier run
        requests = call("GET", "/api/v1/admin/access-requests", admin=True)[1].get("items", [])
        request_id = next(
            (r["id"] for r in requests
             if r.get("requesting_agent_id") == ads and r.get("target_schema_id") == schema
             and r.get("status") == "PENDING"),
            None,
        )
    code, body = call_settled("POST", f"/api/v1/admin/access-requests/{request_id}/approve", {})
    check("approving its access to the per-member schema is refused (403)", code == 403, body)
    show("platform message", body.get("message"))
else:
    print("\nPurpose limitation: re-run with --with-purpose-check (registers a demo advertising agent).")
print(
    "Audit and decision logs: docker compose logs control-plane-api "
    "| grep -E 'memory_write|memory_deletion|memory_decision'"
)
print(f"\n# Result: {PASSED} passed, {FAILED} failed")
raise SystemExit(1 if FAILED else 0)
