#!/usr/bin/env bash
set -euo pipefail

PROGRAM_NAME="$(basename "$0")"

usage() {
  cat <<'EOF'
Enable Google Cloud APIs used by Gemini Enterprise Agent Platform and this
repository's control-plane deployment.

Usage:
  enable_google_agent_platform_apis.sh PROJECT_ID [options]
  enable_google_agent_platform_apis.sh --project-id PROJECT_ID [options]

The required value is the immutable Google Cloud project ID, not the project
display name.

Options:
  --profile core|platform
      core      Agent Platform, Memory Bank, Agent Runtime, Sessions, agent
                evaluation, Gemini Enterprise/Agent Designer, and registry.
      platform  Core plus build/deploy, Cloud Run control plane, Cloud SQL,
                eventing, analytics, and observability APIs (default).

  --with-gateway
      Also enable the current API set documented for Agent Gateway, semantic
      governance, Model Armor, and topology/telemetry integrations.

  --with-classic-model-evaluation
      Also enable Dataflow for classic/batch model-evaluation workflows.
      Agent evaluation itself is already covered by the Agent Platform API.

  --create-service-identities
      Ask Service Usage to create the Agent Platform and Discovery Engine
      service identities after API enablement. This is useful before assigning
      IAM roles to Google-managed service agents.

  --dry-run
      Validate local prerequisites and print mutating gcloud commands without
      executing them.

  -h, --help
      Show this help.

Examples:
  ./scripts/enable_google_agent_platform_apis.sh my-agent-project
  ./scripts/enable_google_agent_platform_apis.sh my-agent-project --dry-run
  ./scripts/enable_google_agent_platform_apis.sh my-agent-project \
    --with-gateway --create-service-identities
EOF
}

log() {
  printf '[%s] %s\n' "$PROGRAM_NAME" "$*"
}

warn() {
  printf '[%s] WARNING: %s\n' "$PROGRAM_NAME" "$*" >&2
}

die() {
  printf '[%s] ERROR: %s\n' "$PROGRAM_NAME" "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

print_command() {
  printf '  +'
  printf ' %q' "$@"
  printf '\n'
}

run_mutation() {
  if [[ "$DRY_RUN" == "true" ]]; then
    print_command "$@"
  else
    "$@"
  fi
}

add_api() {
  local candidate="$1"
  local existing
  for existing in "${ALL_APIS[@]:-}"; do
    if [[ "$existing" == "$candidate" ]]; then
      return
    fi
  done
  ALL_APIS+=("$candidate")
}

add_api_group() {
  local api
  for api in "$@"; do
    add_api "$api"
  done
}

PROJECT_INPUT=""
PROFILE="platform"
WITH_GATEWAY="false"
WITH_CLASSIC_EVALUATION="false"
CREATE_SERVICE_IDENTITIES="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id|--project)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      PROJECT_INPUT="$2"
      shift 2
      ;;
    --profile)
      [[ $# -ge 2 ]] || die "--profile requires core or platform"
      PROFILE="$2"
      shift 2
      ;;
    --with-gateway)
      WITH_GATEWAY="true"
      shift
      ;;
    --with-classic-model-evaluation)
      WITH_CLASSIC_EVALUATION="true"
      shift
      ;;
    --create-service-identities)
      CREATE_SERVICE_IDENTITIES="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -* )
      die "Unknown option: $1"
      ;;
    *)
      [[ -z "$PROJECT_INPUT" ]] || die "Only one project ID may be supplied"
      PROJECT_INPUT="$1"
      shift
      ;;
  esac
done

[[ -n "$PROJECT_INPUT" ]] || {
  usage >&2
  die "A Google Cloud project ID is required"
}

case "$PROFILE" in
  core|platform) ;;
  *) die "Unsupported profile '$PROFILE'; expected core or platform" ;;
esac

require_command gcloud

ACTIVE_ACCOUNTS="$(gcloud auth list --filter='status:ACTIVE' --format='value(account)' 2>/dev/null || true)"
[[ -n "$ACTIVE_ACCOUNTS" ]] || die "No active gcloud account. Run: gcloud auth login"
ACTIVE_ACCOUNT="${ACTIVE_ACCOUNTS%%$'\n'*}"

PROJECT_ID="$(
  gcloud projects describe "$PROJECT_INPUT" \
    --format='value(projectId)' 2>/dev/null
)" || die "Project '$PROJECT_INPUT' was not found or is not visible to $ACTIVE_ACCOUNT"
[[ -n "$PROJECT_ID" ]] || die "Could not resolve a project ID from '$PROJECT_INPUT'"

PROJECT_STATE="$(
  gcloud projects describe "$PROJECT_ID" \
    --format='value(lifecycleState)' 2>/dev/null
)" || die "Unable to read project state for '$PROJECT_ID'"
[[ "$PROJECT_STATE" == "ACTIVE" ]] || die "Project '$PROJECT_ID' is in state '$PROJECT_STATE'"

BILLING_ENABLED="$(
  gcloud billing projects describe "$PROJECT_ID" \
    --format='value(billingEnabled)' 2>/dev/null || true
)"
case "$BILLING_ENABLED" in
  True|true)
    log "Billing is enabled for $PROJECT_ID"
    ;;
  False|false)
    die "Billing is not enabled for '$PROJECT_ID'; link a billing account before using Agent Platform"
    ;;
  *)
    warn "Billing status could not be verified. Confirm billing is linked before creating resources."
    ;;
esac

# Memory Bank, Agent Runtime, Sessions, Code Execution, and Agent Evaluation are
# capabilities of aiplatform.googleapis.com; they do not have separate APIs.
CORE_APIS=(
  serviceusage.googleapis.com
  cloudresourcemanager.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  aiplatform.googleapis.com
  discoveryengine.googleapis.com
  agentregistry.googleapis.com
  storage.googleapis.com
)

# APIs required by the repository's Cloud Run/Cloud SQL control plane and its
# standard build, eventing, analytics, and observability path.
PLATFORM_APIS=(
  artifactregistry.googleapis.com
  cloudbuild.googleapis.com
  run.googleapis.com
  secretmanager.googleapis.com
  compute.googleapis.com
  servicenetworking.googleapis.com
  vpcaccess.googleapis.com
  sqladmin.googleapis.com
  iap.googleapis.com
  pubsub.googleapis.com
  bigquery.googleapis.com
  logging.googleapis.com
  monitoring.googleapis.com
  cloudtrace.googleapis.com
)

# Current documented Agent Gateway prerequisites. These are intentionally
# opt-in because some features may be Preview, allowlisted, or unnecessary for
# projects that only use Runtime, Memory Bank, and evaluation.
GATEWAY_APIS=(
  networksecurity.googleapis.com
  networkservices.googleapis.com
  dns.googleapis.com
  modelarmor.googleapis.com
  observability.googleapis.com
  telemetry.googleapis.com
  apphub.googleapis.com
  apptopology.googleapis.com
  cloudapiregistry.googleapis.com
  notebooks.googleapis.com
  texttospeech.googleapis.com
  dataform.googleapis.com
)

CLASSIC_EVALUATION_APIS=(
  dataflow.googleapis.com
)

ALL_APIS=()
add_api_group "${CORE_APIS[@]}"

if [[ "$PROFILE" == "platform" ]]; then
  add_api_group "${PLATFORM_APIS[@]}"
fi

if [[ "$WITH_GATEWAY" == "true" ]]; then
  add_api_group "${GATEWAY_APIS[@]}"
fi

if [[ "$WITH_CLASSIC_EVALUATION" == "true" ]]; then
  add_api_group "${CLASSIC_EVALUATION_APIS[@]}"
fi

log "Active account: $ACTIVE_ACCOUNT"
log "Target project: $PROJECT_ID"
log "Profile: $PROFILE"
log "APIs selected: ${#ALL_APIS[@]}"

if [[ "$DRY_RUN" == "true" ]]; then
  log "Dry run; the following command would be executed:"
else
  log "Enabling APIs. This operation is idempotent and can take several minutes."
fi

run_mutation gcloud services enable \
  "${ALL_APIS[@]}" \
  --project="$PROJECT_ID" \
  --quiet

if [[ "$CREATE_SERVICE_IDENTITIES" == "true" ]]; then
  for service_name in aiplatform.googleapis.com discoveryengine.googleapis.com; do
    if [[ "$DRY_RUN" == "true" ]]; then
      log "Service identity command for $service_name:"
    else
      log "Creating or confirming the service identity for $service_name"
    fi
    run_mutation gcloud beta services identity create \
      --service="$service_name" \
      --project="$PROJECT_ID"
  done
fi

if [[ "$DRY_RUN" == "false" ]]; then
  ENABLED_SERVICES="$(
    gcloud services list \
      --enabled \
      --project="$PROJECT_ID" \
      --format='value(config.name)'
  )"

  MISSING_COUNT=0
  for api in "${ALL_APIS[@]}"; do
    if ! printf '%s\n' "$ENABLED_SERVICES" | grep -Fqx "$api"; then
      warn "API was not reported as enabled: $api"
      MISSING_COUNT=$((MISSING_COUNT + 1))
    fi
  done

  [[ "$MISSING_COUNT" -eq 0 ]] || die "$MISSING_COUNT selected API(s) could not be verified"
  log "Verified all ${#ALL_APIS[@]} selected APIs as enabled."
fi

if [[ "$DRY_RUN" == "true" ]]; then
  COMPLETION_MESSAGE="Dry run is complete; no APIs or service identities were changed for project: $PROJECT_ID"
else
  COMPLETION_MESSAGE="API enablement is complete for project: $PROJECT_ID"
fi

cat <<EOF

$COMPLETION_MESSAGE

This script does not:
  - create a Gemini Enterprise application or turn on the Agent Designer UI;
  - create an Agent Runtime deployment, Memory Bank, evaluation run, or registry entry;
  - link billing, grant IAM roles, request Preview/allowlist access, or select a region;
  - provision this repository's Cloud Run, Cloud SQL, networking, or other resources.

Required follow-up:
  1. Grant operators Agent Platform User (roles/aiplatform.user).
  2. Grant memory callers Memory Bank User (roles/aiplatform.memoryUser), scoped
     more narrowly with IAM Conditions where appropriate.
  3. Grant Gemini Enterprise administrators the product-specific admin role.
  4. Create the Gemini Enterprise app and enable Agent Designer in its end-user
     feature controls if that experience is required.
  5. Use Terraform in infrastructure/ for durable environment provisioning.
  6. Choose a supported location before creating Runtime, Memory Bank, Sessions,
     Registry, or Gateway resources.
EOF
