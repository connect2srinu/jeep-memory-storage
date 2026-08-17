from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.shared_memory.contracts import ContractValidationError, compile_contracts, load_contracts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview a domain's validated contract and generated platform artifacts."
    )
    parser.add_argument("--domain", default="grocery")
    parser.add_argument("--contracts-dir", type=Path, default=Path("config/contracts"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        bundle = load_contracts(args.contracts_dir)
    except ContractValidationError as exc:
        raise SystemExit(str(exc)) from exc

    domain = next(
        (item for item in bundle.domains if item.metadata.name == args.domain), None
    )
    if domain is None:
        available = ", ".join(sorted(str(item.metadata.name) for item in bundle.domains))
        raise SystemExit(f"Unknown domain {args.domain!r}. Available: {available}")

    preferences = [
        preference
        for catalog in bundle.catalogs
        if catalog.metadata.domain == args.domain
        for preference in catalog.preferences
    ]
    profiles = [
        profile
        for contract in bundle.profiles
        for profile in contract.profiles
        if profile.owner_domain == args.domain
    ]
    consumers = [
        consumer
        for contract in bundle.consumers
        for consumer in contract.consumers
        if consumer.consumer_domain == args.domain
    ]
    compilation = compile_contracts(bundle)
    summary = {
        "domain": args.domain,
        "read_domains": domain.spec.permissions.read,
        "write_domains": domain.spec.permissions.write,
        "canonical_preferences": [item.key for item in preferences],
        "memory_profiles": [item.id for item in profiles],
        "consumers": [item.agent_id for item in consumers],
        "generated_artifacts": [
            path.as_posix()
            for path in sorted(compilation.artifacts, key=lambda item: item.as_posix())
        ],
        "next_commands": [
            "python scripts/compile_memory_contract.py",
            "python scripts/compile_memory_contract.py --check",
            "python scripts/deploy.py  # cloud mutation after review and approval",
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
