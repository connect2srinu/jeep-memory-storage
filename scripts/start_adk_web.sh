#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and configure the Google Cloud values." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

session_resource="${AGENT_PLATFORM_SESSIONS_ID:-${GOOGLE_CLOUD_AGENT_ENGINE_ID:-}}"
memory_resource="${AGENT_PLATFORM_MEMORY_BANK_ID:-${GOOGLE_CLOUD_AGENT_ENGINE_ID:-}}"

if [[ -z "$session_resource" || -z "$memory_resource" ]]; then
  echo "Configure AGENT_PLATFORM_SESSIONS_ID, AGENT_PLATFORM_MEMORY_BANK_ID, or GOOGLE_CLOUD_AGENT_ENGINE_ID." >&2
  exit 1
fi

if [[ -x .venv/bin/adk ]]; then
  adk_command=.venv/bin/adk
else
  adk_command="$(command -v adk || true)"
fi

if [[ -z "$adk_command" ]]; then
  echo "ADK is not installed. Run: python -m pip install -e '.[dev]'" >&2
  exit 1
fi

host="${ADK_WEB_HOST:-0.0.0.0}"
port="${ADK_WEB_PORT:-8000}"

echo "Starting ADK Web at http://localhost:${port}"
exec "$adk_command" web . \
  --host "$host" \
  --port "$port" \
  --session_service_uri="agentengine://${session_resource}" \
  --memory_service_uri="agentengine://${memory_resource}"
