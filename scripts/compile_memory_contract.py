from __future__ import annotations

import argparse
from pathlib import Path

from app.shared_memory.contracts import (
    ContractValidationError,
    compile_contracts,
    load_contracts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile domain YAML contracts into deterministic runtime artifacts."
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=Path("config/contracts"),
        help="Directory containing per-domain YAML bundles.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Project root where generated artifacts are checked or written.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if checked-in generated artifacts differ; do not write files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        bundle = load_contracts(args.contracts_dir)
    except ContractValidationError as exc:
        raise SystemExit(str(exc)) from exc
    compilation = compile_contracts(bundle)
    if args.check:
        differences = compilation.differences(args.project_root)
        if differences:
            raise SystemExit(
                "Generated memory artifacts are out of date:\n- " + "\n- ".join(differences)
            )
        print(f"Generated memory artifacts are current ({len(compilation.artifacts)} files).")
        return
    compilation.write(args.project_root)
    print(f"Compiled {len(compilation.artifacts)} memory contract artifacts.")


if __name__ == "__main__":
    main()
