# Deployment and Operations Runbook

## Safety boundary

Terraform, cloud deployment, schema provisioning, live memory writes, and teardown mutate external
state. Run them only in the intended project/environment with reviewed placeholders and approvals.

## 1. Validate

```bash
python scripts/validate_memory_contract.py --source config/contracts
python scripts/compile_memory_contract.py --source config/contracts --output config/generated --check

PYTHONPATH=apps/memory-api/app:. .venv/bin/python -m pytest -q apps/memory-api/tests
PYTHONPATH=apps/reference-agent/app:. .venv/bin/python -m pytest -q apps/reference-agent/tests

cd apps/admin-console
npm run typecheck
npm test
npm run build
```

## 2. Configure

Complete [Deployment Placeholders](deployment-placeholders.md). Confirm the GCP project, region,
Agent Engine resource, identities, database, image tags, token audiences, and admin role bindings.

## 3. Deploy

1. apply reviewed infrastructure changes;
2. run database migrations;
3. deploy Memory API and wait for `/healthz`;
4. deploy Admin Console;
5. deploy or configure consumer agents;
6. bootstrap existing reviewed contracts;
7. activate/provision new domain schemas;
8. approve required shared-schema access.

The Memory API must use `MEMORY_BACKEND=vertex` in the cloud-backed environment. Successful guided
activation returns `PROVISIONED`; `REGISTERED_LOCAL` is not an acceptable production result.

## 4. Smoke test

Use a dedicated test user and domain:

1. resolve and verify `writablePreferences`;
2. submit an update without `schemaId`;
3. confirm the correct same-domain schema was selected;
4. resolve in a later Session;
5. verify another user cannot read it;
6. verify a shared read-only schema cannot be written;
7. inspect audit and correlation IDs.

Allow for asynchronous managed-profile consolidation. Do not repeatedly create profiles when
polling; use read-only resolve/inspection.

## 5. Observe

Monitor API availability, latency, `4xx`/`5xx` rates, authorization denials, ambiguous/unknown write
routing, provider operations, database saturation, schema provisioning failures, and audit volume.
Do not log raw sensitive preference values unless an approved policy explicitly allows it.

## 6. Roll back

Roll back application images first. Revoke/retire new grants and policies or restore the prior active
schema version; do not delete Memory Bank data as a deployment rollback. Correct user data through
audited owner-domain operations.

## 7. Teardown

Resolve exact targets before destruction. Preserve required exports and audit evidence, revoke
access, drain traffic, remove applications, then remove infrastructure according to retention policy.
