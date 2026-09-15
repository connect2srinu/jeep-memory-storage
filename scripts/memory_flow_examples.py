#!/usr/bin/env python3
"""Runnable examples exercising the memory flows against the Control Plane runtime API.

Covers: canonical writes, dynamic topic gating, restricted-content blocking, the sensitive +
source rule, admin-declared per-topic sensitivity, resolve surfacing (sensitivity, memorySource,
approvedTopicDetails), and deletion (forget + a non-destructive purge preview).

Assumes the local stack is up (control plane on :8080) and the `grocery` domain's dynamic-memory
policy approves topics `shopping`, `fulfillment`, and `wellness:sensitive`. Configure via the admin
console (Create Memory Setup) or:
  UPDATE dynamic_memory_policies SET memory_topics='["shopping","fulfillment","wellness:sensitive"]'::json WHERE domain_id='grocery';

Usage:  python3 scripts/memory_flow_examples.py [--base http://localhost:8080] [--agent grocery-agent] [--domain grocery]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

ARGS = argparse.ArgumentParser(description=__doc__)
ARGS.add_argument("--base", default="http://localhost:8080")
ARGS.add_argument("--agent", default="grocery-agent")
ARGS.add_argument("--domain", default="grocery")
OPTS = ARGS.parse_args()

USER = f"flow-{int(time.time())}"
PASSED = 0
FAILED = 0


def call(method: str, path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        OPTS.base + path,
        data=json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json", "X-Agent-ID": OPTS.agent},
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.getcode(), json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def scope() -> dict:
    return {"userId": USER, "appName": "examples", "domain": OPTS.domain}


def dynamic(topic: str, value: str, source: str | None = None) -> tuple[int, dict]:
    body = {"scope": scope(), "topic": topic, "value": value}
    if source:
        body["source"] = source
    return call("POST", "/api/v1/runtime/memory/dynamic", body)


def canonical(attribute: str, value: str, source: str | None = None) -> tuple[int, dict]:
    body = {"scope": scope(), "value": value}
    if source:
        body["source"] = source
    return call("PUT", f"/api/v1/runtime/preferences/{attribute}", body)


def resolve() -> dict:
    return call(
        "POST",
        "/api/v1/runtime/preferences/resolve",
        {"scope": scope(), "sessionId": "s", "agentId": OPTS.agent},
    )[1]


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}  -- {detail}")


def expect(label: str, result: tuple[int, dict], code: int) -> dict:
    got, body = result
    msg = body.get("message", "") if isinstance(body, dict) else ""
    check(label, got == code, f"expected {code}, got {got} {msg}")
    return body


print(f"# Memory flow examples  (user={USER}, agent={OPTS.agent}, domain={OPTS.domain})\n")

print("## 1 · Canonical memory (structured, governed)")
expect("save canonical preferred_store", canonical("grocery.preferred_store", "Kroger"), 200)
expect("PII in a canonical value is restricted (400)", canonical("grocery.preferred_store", "call me at 555-123-4567"), 400)

print("\n## 2 · Dynamic memory — topic gating")
expect("approved topic 'shopping' is stored", dynamic("shopping", "shops early Sunday mornings"), 200)
expect("unapproved topic 'garden' is rejected (403)", dynamic("garden", "grows tomatoes"), 403)

print("\n## 3 · Restricted content is blocked on all writes")
expect("weapons -> restricted (400)", dynamic("shopping", "wishes he could bring guns in"), 400)
expect("discriminatory targeting -> restricted (400)", dynamic("shopping", "don't let a certain person pick my order"), 400)

print("\n## 4 · Sensitive content + source rule")
expect("protected-class inferred -> rejected (403)", dynamic("shopping", "user is Muslim", "inference"), 403)
expect("protected-class user-directed -> stored (200)", dynamic("shopping", "user is Muslim", "user_directed"), 200)

print("\n## 5 · Admin-declared per-topic sensitivity ('wellness:sensitive')")
expect("sensitive topic + inferred -> rejected (403)", dynamic("wellness", "walks daily", "inference"), 403)
expect("sensitive topic + user-directed -> stored (200)", dynamic("wellness", "walks daily", "user_directed"), 200)

print("\n## 6 · Resolve surfaces classification + topic meaning")
snap = resolve()
prefs = snap.get("preferences", {})
check("preferred_store resolved (canonical)", prefs.get("preferred_store", {}).get("value") == "Kroger",
      json.dumps(prefs.get("preferred_store")))
shopping = prefs.get("topic:shopping", {})
check("topic:shopping is DYNAMIC_MEMORY", shopping.get("source") == "DYNAMIC_MEMORY", json.dumps(shopping))
check("topic:shopping carries sensitivity", shopping.get("sensitivity") in {"normal", "sensitive"}, json.dumps(shopping))
check("topic:wellness surfaces as sensitive", prefs.get("topic:wellness", {}).get("sensitivity") == "sensitive",
      json.dumps(prefs.get("topic:wellness")))
details = {d.get("topic"): d for d in snap.get("approvedTopicDetails", [])}
check("approvedTopicDetails present with meanings", bool(details) and "shopping" in details, json.dumps(details))

print("\n## 7 · Deletion (governance / CCPA)")
purge_code, purge_body = call("POST", "/api/v1/runtime/memory/purge", {"topic": "shopping", "dryRun": True})
check("operator purge dry-run (200 preview, or 403 if agent lacks ADMINISTER_MEMORY)",
      purge_code in {200, 403}, f"got {purge_code} {purge_body.get('message','')}")
expect("forget deletes this user's memories", call("POST", "/api/v1/runtime/memory/forget", {"scope": scope()}), 200)
time.sleep(4)  # Memory Bank reads are eventually consistent
after = resolve().get("preferences", {})
check("resolve is empty after forget", after == {}, json.dumps(after))

print(f"\n# Result: {PASSED} passed, {FAILED} failed")
raise SystemExit(1 if FAILED else 0)
