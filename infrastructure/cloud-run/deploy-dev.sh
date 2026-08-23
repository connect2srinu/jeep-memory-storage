#!/usr/bin/env bash
set -euo pipefail

environment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../terraform/environments/dev" && pwd)"
cd "${environment_dir}"

terraform init
terraform fmt -check -recursive ../..
terraform validate
terraform plan -out=dev.tfplan

printf 'Plan saved to %s/dev.tfplan. Review it before running terraform apply dev.tfplan.\n' "${environment_dir}"
