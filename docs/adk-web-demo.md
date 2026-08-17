# ADK Web Shared Memory demo

This demo validates the Grocery reference consumer against managed Agent Platform Sessions,
explicit mock profiles, Memory Profiles when configured, and Memory Bank dynamic memory.

## Start ADK Web

```bash
cd ~/projects/geap/geap-memory
source .venv/bin/activate
./scripts/start_adk_web.sh
```

Open <http://localhost:8000>, select `app`, and use `user-123` as the user ID. Create a new
session for the first four flows. In diagnostics, expect each preference to include `value`,
`source`, `owner_domain`, and `resolution_reason`.

## Flow 1: explicit profile baseline

Prompt:

```text
What preferences are you currently using? Show value, source, owner domain, and resolution reason.
```

Expected highlights:

```text
customer.diet = vegetarian, source = EXPLICIT_PROFILE, owner = customer
customer.preferred_store = Kroger, source = EXPLICIT_PROFILE, owner = customer
grocery.preferred_milk = whole milk, source = EXPLICIT_PROFILE, owner = grocery
grocery.allow_substitutions = false, source = EXPLICIT_PROFILE, owner = grocery
```

## Flow 2: session override

Prompt:

```text
For today's shopping trip, substitutions are okay.
```

Then ask:

```text
What preferences are you currently using? Explain allow_substitutions.
```

Expected: `grocery.allow_substitutions = true` with source `SESSION_OVERRIDE`. The explicit
profile remains `false`, but loses for this session.

## Flow 3: session isolation

Create a new session for the same `user-123`, then ask:

```text
What is my allow_substitutions preference and why?
```

Expected: the new session returns the explicit-profile value `false`. The previous temporary
override must not leak into the new session.

## Flow 4: dynamic long-term preference

Prompt:

```text
I usually prefer bananas that are slightly green.
```

Then ask:

```text
What banana ripeness preference are you using? Show its source and owner domain.
```

Expected: `grocery.banana_ripeness = slightly_green`, source `DYNAMIC_MEMORY`, owner `grocery`.
Create another new session and repeat the question. The value should persist because it was
written to long-term Memory Bank, not Session state.

## Flow 5: canonical long-term preference

Prompt:

```text
I always prefer organic produce.
```

Then ask:

```text
What organic preference are you using and where did it come from?
```

Expected: the catalog recognizes `grocery.organic_preference` as canonical. In this POC it is
persisted through the authorized long-term Memory Bank adapter. An enterprise profile-owner
workflow can later route canonical updates to an authoritative profile system.

## Flow 6: cross-domain write protection

Prompt:

```text
I prefer evening delivery.
```

Expected: Grocery detects `delivery.preferred_window`, but the platform returns a
`CANDIDATE_ROUTED` result. Grocery has read access to Delivery but cannot write Delivery memory.

Then ask:

```text
Did you directly update my delivery preference? Explain the policy result.
```

Expected: no direct Delivery write occurred.

## Flow 7: backend inspection

Copy the session ID shown by ADK Web and run:

```bash
python scripts/inspect_state.py --user-id user-123 --session-id SESSION_ID
python scripts/inspect_memory.py --user-id user-123 --domains grocery,customer,delivery
```

The Session result should show structured state under `shared_memory:preferences`. Memory
inspection should distinguish normalized dynamic memories from structured Memory Profiles.

## Flow 8: deterministic full scenario

ADK Web demonstrates live tool and backend behavior. Run the deterministic acceptance scenario
separately to validate all expected conflict winners without relying on previously accumulated
cloud state:

```bash
python scripts/validate_platform.py
```

Expected final line:

```text
Shared Memory Platform final scenario: PASS
```

## Reset guidance

Use a fresh user ID or remove only the specific test memories through an approved lifecycle tool
before repeating persistence tests. Creating a new ADK session resets session overrides but does
not delete Memory Bank entries.
