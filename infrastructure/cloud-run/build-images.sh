#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_LOCATION:?Set GOOGLE_CLOUD_LOCATION}"
: "${ARTIFACT_REPOSITORY:?Set ARTIFACT_REPOSITORY}"
: "${IMAGE_TAG:?Set IMAGE_TAG to an immutable commit SHA or release tag}"

registry="${GOOGLE_CLOUD_LOCATION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${ARTIFACT_REPOSITORY}"

gcloud auth configure-docker "${GOOGLE_CLOUD_LOCATION}-docker.pkg.dev" --quiet
docker build -f apps/memory-api/Dockerfile -t "${registry}/memory-api:${IMAGE_TAG}" .
docker build -f apps/reference-agent/Dockerfile -t "${registry}/reference-agent:${IMAGE_TAG}" .
docker build --build-arg VITE_MEMORY_API_URL=/api/v1/admin \
  -f apps/admin-console/Dockerfile -t "${registry}/admin-console:${IMAGE_TAG}" .
docker push "${registry}/memory-api:${IMAGE_TAG}"
docker push "${registry}/reference-agent:${IMAGE_TAG}"
docker push "${registry}/admin-console:${IMAGE_TAG}"

printf 'Images pushed under %s with tag %s\n' "${registry}" "${IMAGE_TAG}"
