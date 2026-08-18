# ADK Web Shared Memory demo

This demo validates the Grocery reference consumer against managed Agent Platform Sessions,
explicit mock profiles, Memory Profiles when configured, and Memory Bank dynamic memory.

Use separate synthetic users for UI-write and profile-generation demonstrations. Reusing one user
for both intentionally creates competing `DOMAIN_MEMORY` and `MEMORY_PROFILE` candidates, and the
configured resolver policy decides which value is effective.

## Validate configuration before the demo

```bash
cd ~/projects/geap/geap-memory
source .venv/bin/activate
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
```

When Memory Profile YAML or runtime code changed, deploy the reviewed build before running cloud
generation:

```bash
set -a
source .env
set +a
python scripts/deploy.py
```

Keep `GOOGLE_CLOUD_AGENT_ENGINE_ID` set to the existing resource ID. Leaving it empty takes the
create path instead of updating the existing Agent Runtime.

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

## Flow 6: Grocery Snack preference from ADK Web

For this flow, use a synthetic user such as `snack-ui-demo-001` with no previously generated Snack
profile. Create a new ADK Web session and enter:

```text
I always prefer mango chips as my snack.
```

Expected tool result:

```text
status = STORED_IN_DYNAMIC_MEMORY
canonical_key = grocery.preferred_snack
owner_domain = grocery
value = mango_chips
requested_scope = LONG_TERM
```

Then ask:

```text
What Snack preference are you currently using? Show the value, source, owner domain,
resolution reason, and policy ID.
```

Expected: `grocery.preferred_snack = mango_chips`, owned by Grocery. The long-term UI path writes a
canonical Grocery domain-memory record; it does not directly regenerate the structured Memory
Profile.

For a temporary test, use:

```text
For today, use pretzels as my snack.
```

Expected: `STORED_IN_SESSION` and source `SESSION_OVERRIDE`. A new session must not contain the
temporary value.

Inspect the UI-created long-term record:

```bash
python scripts/inspect_memory.py \
  --user-id snack-ui-demo-001 \
  --domains grocery
```

Expected location: `dynamic_memories`, with key `grocery.preferred_snack`, owner `grocery`, and
source `DOMAIN_MEMORY`.

## Flow 7: create a structured Memory Profile from the command line

Profile schema deployment and user profile generation are separate operations. Use a different
synthetic user so this flow does not conflict with the UI domain-memory demonstration:

```bash
python scripts/generate_profile.py \
  --user-id snack-profile-demo-001 \
  --domain grocery \
  --text "I always prefer mango chips as my snack."
```

Expected submission message:

```text
Memory generation submitted for scope {
  'user_id': 'snack-profile-demo-001',
  'app_name': 'grocery_shared_preferences',
  'domain': 'grocery'
}; configured profiles: grocery-preferences-v1
```

Generation uses the exact scope `user_id + app_name + domain`. Changing any one of those values
targets a different profile scope.

Inspect normalized Memory Bank output:

```bash
python scripts/inspect_memory.py \
  --user-id snack-profile-demo-001 \
  --domains grocery
```

Expected location: `memory_profiles`.

```json
{
  "key": "grocery.preferred_snack",
  "value": "mango chips",
  "source": "MEMORY_PROFILE",
  "owner_domain": "grocery",
  "scope": "LONG_TERM",
  "provenance": {
    "schema_id": "grocery-preferences-v1"
  }
}
```

The platform adapter admits a structured value only when all of these agree:

```text
requested domain = grocery
schema owner = grocery
canonical key owner = grocery
schema ID = grocery-preferences-v1
```

Google may evaluate other schemas that share the same scope-key signature. The adapter must reject
Customer, Store, Delivery, unknown-schema, unknown-field, and catalog-owner-mismatch results. They
must not appear in normalized Grocery inspection or effective context.

## Flow 8: update an existing structured Memory Profile

Submit another confirmed statement using the exact same user, application, domain, resource, and
schema:

```bash
python scripts/generate_profile.py \
  --user-id snack-profile-demo-001 \
  --domain grocery \
  --text "I always prefer potato chips as my snack."
```

Inspect again:

```bash
python scripts/inspect_memory.py \
  --user-id snack-profile-demo-001 \
  --domains grocery
```

Expected: the maintained `grocery-preferences-v1` profile for that exact scope reflects the
consolidated Snack value. Do not assume profile creation or update from the submission message
alone; use inspection to verify it.

## Flow 9: inspect managed Session state

Copy the session ID shown by ADK Web and run:

```bash
python scripts/inspect_state.py \
  --user-id snack-ui-demo-001 \
  --session-id SESSION_ID
```

Session preferences appear under `shared_memory:preferences`. Long-term domain memory and Memory
Profiles do not belong in Session state.

## Flow 10: inspect several authorized domains

```bash
python scripts/inspect_memory.py \
  --user-id USER_ID \
  --domains grocery,customer,store,delivery
```

This command performs one exact-scope retrieval for each requested domain. A preference may appear
only when its schema owner, canonical owner, and requested domain agree. Use a single domain when
validating isolation.

## Flow 11: cross-domain write protection

Prompt:

```text
I prefer evening delivery.
```

Expected: Grocery detects `delivery.preferred_window`, but the platform returns a
`CROSS_DOMAIN_CANDIDATE` result. Grocery has read access to Delivery but cannot write Delivery
memory.

Then ask:

```text
Did you directly update my delivery preference? Explain the policy result.
```

Expected: no direct Delivery write occurred.

## Flow 12: deterministic full scenario

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

## Interpreting inspection output

| Output section | Meaning |
|---|---|
| `dynamic_memories` | Authorized long-term domain facts created through UI/tools or seed flow |
| `memory_profiles` | Structured schema-backed values created through profile generation/sync |
| Session `shared_memory:preferences` | Temporary values tied to one managed session |

If the same logical preference exists in several sources, inspect the effective context as well as
the raw normalized source records. The default source order is:

```text
SESSION_OVERRIDE
> EXPLICIT_PROFILE
> MEMORY_PROFILE
> DOMAIN_MEMORY
> DYNAMIC_MEMORY
> INFERRED_MEMORY
> DEFAULT
```

For example, a CLI-generated Snack Memory Profile can outrank a different Snack value written as
UI domain memory. That is expected under the current policy and is separate from whether the UI
write succeeded.

## Reset guidance

Use a fresh user ID or remove only the specific test memories through an approved lifecycle tool
before repeating persistence tests. Creating a new ADK session resets session overrides but does
not delete Memory Bank entries.

The current repository does not provide a production deletion workflow. Do not delete broad scopes
or production user data during a demo.
