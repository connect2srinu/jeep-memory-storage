from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_memory_api_has_independent_health_entrypoint() -> None:
    path = PROJECT_ROOT / "apps" / "memory-api" / "app" / "memory_api" / "main.py"
    spec = importlib.util.spec_from_file_location("memory_api_phase_one", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    response = TestClient(module.app).get("/healthz")
    assert response.json() == {"status": "ok", "application": "memory-api"}


def test_three_application_manifests_exist() -> None:
    assert (PROJECT_ROOT / "apps" / "reference-agent" / "pyproject.toml").is_file()
    assert (PROJECT_ROOT / "apps" / "memory-api" / "pyproject.toml").is_file()
    package = json.loads(
        (PROJECT_ROOT / "apps" / "admin-console" / "package.json").read_text()
    )
    assert package["name"] == "shared-memory-admin-console"


def test_reference_agent_has_no_memory_bank_sdk_imports() -> None:
    source_root = PROJECT_ROOT / "apps" / "reference-agent" / "app"
    source = "\n".join(path.read_text() for path in source_root.rglob("*.py"))
    assert "agentplatform" not in source
    assert "vertexai" not in source
