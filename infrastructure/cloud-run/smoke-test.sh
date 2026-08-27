#!/usr/bin/env bash
set -euo pipefail

: "${CONTROL_PLANE_API_URL:?Set CONTROL_PLANE_API_URL to the direct Cloud Run service URL}"
: "${REFERENCE_AGENT_URL:?Set REFERENCE_AGENT_URL to the direct Cloud Run service URL}"

identity_token="$(gcloud auth print-identity-token)"

curl --fail --silent --show-error \
  -H "Authorization: Bearer ${identity_token}" "${CONTROL_PLANE_API_URL}/healthz"
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${identity_token}" "${REFERENCE_AGENT_URL}/"

printf '\nSmoke checks passed. Run scripts/run_phase9_acceptance.py for the governed data flow.\n'
