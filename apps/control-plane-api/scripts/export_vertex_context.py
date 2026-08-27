from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.persistence import Database
from control_plane_api.services.vertex_provisioning import build_vertex_context_spec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export approved active control-plane schemas as Vertex context_spec JSON."
    )
    parser.add_argument("--output", type=Path, help="Write JSON to this path; stdout if omitted.")
    return parser.parse_args()


async def export(output: Path | None) -> None:
    settings = ControlPlaneApiSettings.from_environment()
    database = Database(settings.database_url)
    try:
        async with database.session() as session:
            payload = await build_vertex_context_spec(session)
    finally:
        await database.dispose()
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(content, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"Wrote Vertex context spec to {output}")


if __name__ == "__main__":
    asyncio.run(export(parse_args().output))
