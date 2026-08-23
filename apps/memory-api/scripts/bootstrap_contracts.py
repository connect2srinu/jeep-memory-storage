from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from app.shared_memory.contracts import load_contracts
from memory_api.persistence import Database
from memory_api.services import ContractBootstrapService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import validated YAML into the control plane.")
    parser.add_argument("--contracts-dir", type=Path, default=Path("config/contracts"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--create-schema", action="store_true")
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("Set DATABASE_URL or pass --database-url")
    bundle = load_contracts(args.contracts_dir)
    database = Database(args.database_url)
    try:
        if args.create_schema:
            await database.create_schema()
        async with database.session() as session:
            result = await ContractBootstrapService(session).import_bundle(bundle)
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(run())
