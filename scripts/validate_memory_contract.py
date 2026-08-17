from __future__ import annotations

import argparse
from pathlib import Path

from app.shared_memory.contracts import ContractValidationError, load_contracts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Shared Memory Platform domain contracts without writing files."
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=Path("config/contracts"),
        help="Directory containing per-domain YAML bundles.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        bundle = load_contracts(args.contracts_dir)
    except ContractValidationError as exc:
        raise SystemExit(str(exc)) from exc
    preference_count = sum(len(item.preferences) for item in bundle.catalogs)
    profile_count = sum(len(item.profiles) for item in bundle.profiles)
    consumer_count = sum(len(item.consumers) for item in bundle.consumers)
    print(
        "Memory contracts valid: "
        f"{len(bundle.domains)} domains, {preference_count} preferences, "
        f"{profile_count} profiles, {consumer_count} consumers, "
        f"{len(bundle.source_files)} YAML files."
    )


if __name__ == "__main__":
    main()
