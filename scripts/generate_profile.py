from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.shared_memory.contracts import ContractValidationError, load_contracts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate configured Memory Profiles from an explicit demo event."
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--text", required=True, help="Explicit event text sent to Memory Bank.")
    parser.add_argument("--app-name", default=settings.app_name)
    parser.add_argument("--contracts-dir", type=Path, default=Path("config/contracts"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = settings.project
    resource_id = settings.memory_resource_id
    if not project or not resource_id:
        raise SystemExit(
            "Configure GOOGLE_CLOUD_PROJECT and AGENT_PLATFORM_MEMORY_BANK_ID "
            "or GOOGLE_CLOUD_AGENT_ENGINE_ID in .env."
        )

    try:
        bundle = load_contracts(args.contracts_dir)
    except ContractValidationError as exc:
        raise SystemExit(str(exc)) from exc
    profiles = [
        profile
        for contract in bundle.profiles
        for profile in contract.profiles
        if profile.owner_domain == args.domain and profile.generation.enabled
    ]
    if not profiles:
        raise SystemExit(f"No enabled Memory Profile contract for domain {args.domain!r}")

    import agentplatform

    client = agentplatform.Client(project=project, location=settings.location)
    name = (
        f"projects/{project}/locations/{settings.location}/reasoningEngines/{resource_id}"
    )
    scope = {
        "user_id": args.user_id,
        "app_name": args.app_name,
        "domain": args.domain,
    }
    client.agent_engines.memories.generate(
        name=name,
        scope=scope,
        direct_contents_source={
            "events": [{"content": {"parts": [{"text": args.text}]}}]
        },
    )
    profile_ids = ", ".join(profile.id for profile in profiles)
    print(f"Memory generation submitted for scope {scope}; configured profiles: {profile_ids}")


if __name__ == "__main__":
    main()
