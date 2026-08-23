from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    errors: list[str] = []
    infrastructure = ROOT / "infrastructure"
    for path in infrastructure.rglob("*"):
        if (
            not path.is_file()
            or ".terraform" in path.parts
            or path.suffix not in {".tf", ".sh", ".yaml", ".yml", ".md", ".example"}
        ):
            continue
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if "allUsers" in text:
            errors.append(f"{relative}: public allUsers binding is forbidden")
        if re.search(r"AUTH_ENABLED[^\n]*(false|0)", text, re.IGNORECASE):
            errors.append(f"{relative}: deployed authentication cannot be disabled")
        if re.search(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----", text):
            errors.append(f"{relative}: private key material is forbidden")
    for dockerfile in ROOT.glob("apps/*/Dockerfile"):
        text = dockerfile.read_text(encoding="utf-8")
        if re.search(r"^COPY\s+.*\.env", text, re.MULTILINE):
            errors.append(f"{dockerfile.relative_to(ROOT)}: images must not copy .env files")
    example = (
        ROOT / "infrastructure" / "terraform" / "environments" / "dev" / "terraform.tfvars.example"
    ).read_text(encoding="utf-8")
    required = {
        "<GCP_PROJECT_ID>",
        "<IAP_OAUTH_CLIENT_SECRET>",
        "<AGENT_PLATFORM_MEMORY_BANK_ID>",
        "<REFERENCE_AGENT_SERVICE_ACCOUNT_EMAIL>",
    }
    missing = sorted(item for item in required if item not in example)
    if missing:
        errors.append(f"terraform.tfvars.example is missing placeholders: {missing}")
    if errors:
        raise SystemExit("Deployment security validation failed:\n- " + "\n- ".join(errors))
    print("Deployment security validation passed.")


if __name__ == "__main__":
    main()
