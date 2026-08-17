from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

from app.agent import app
from app.config import settings
from app.shared_memory.contracts import compile_contracts, load_contracts

DISPLAY_NAME = "grocery-shared-preferences-poc"
REQUIREMENTS = [
    "google-adk[gcp]>=2.0.0,<3.0.0",
    "google-cloud-aiplatform[agent_engines,adk]>=1.112.0,<3.0.0",
    "python-dotenv>=1.0.1,<2.0.0",
    "fastapi>=0.116,<1.0",
    "uvicorn[standard]>=0.35,<1.0",
]


def ensure_memory_contracts_current() -> None:
    project_root = Path(__file__).resolve().parents[1]
    bundle = load_contracts(project_root / "config" / "contracts")
    differences = compile_contracts(bundle).differences(project_root)
    if differences:
        detail = "\n- ".join(differences)
        raise SystemExit(
            "Memory contract artifacts are stale. Run "
            f"python scripts/compile_memory_contract.py before deployment:\n- {detail}"
        )


def memory_profile_context_spec() -> dict[str, object]:
    """Load compiled per-domain schemas; dynamic preferences remain natural-language memories."""
    path = files("app.shared_memory.profiles").joinpath("memory_profiles.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "memory_bank_config": {
            "structured_memory_configs": payload["structured_memory_configs"]
        }
    }


def ensure_staging_bucket(bucket_uri: str, project: str, location: str) -> None:
    from google.cloud import storage

    parsed = urlparse(bucket_uri)
    if parsed.scheme != "gs" or not parsed.netloc or parsed.path not in {"", "/"}:
        raise SystemExit("AGENT_PLATFORM_STAGING_BUCKET must look like gs://bucket-name")
    client = storage.Client(project=project)
    bucket = client.bucket(parsed.netloc)
    if bucket.exists():
        print(f"Using existing staging bucket: {bucket_uri}")
        return
    client.create_bucket(bucket, location=location)
    print(f"Created staging bucket: {bucket_uri}")


def main() -> None:
    import agentplatform
    from agentplatform import types
    from vertexai.agent_engines import AdkApp

    ensure_memory_contracts_current()
    if not settings.project or not settings.staging_bucket:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT and AGENT_PLATFORM_STAGING_BUCKET")
    ensure_staging_bucket(settings.staging_bucket, settings.project, settings.location)
    client = agentplatform.Client(project=settings.project, location=settings.location)
    deployment_config = {
        "display_name": DISPLAY_NAME,
        "staging_bucket": settings.staging_bucket,
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "requirements": REQUIREMENTS,
        # The serialized tools import our local app package. Object deployment
        # must upload that package alongside agent_engine.pkl.
        "extra_packages": ["app"],
    }
    if settings.enable_memory_profiles:
        deployment_config["context_spec"] = memory_profile_context_spec()
    existing_id = settings.agent_engine_id
    if existing_id:
        resource_name = (
            f"projects/{settings.project}/locations/{settings.location}/"
            f"reasoningEngines/{existing_id}"
        )
        print(f"Updating existing Agent Runtime: {resource_name}")
        deployed = client.agent_engines.update(
            name=resource_name,
            agent=AdkApp(app=app),
            config=deployment_config,
        )
    else:
        deployed = client.agent_engines.create(
            agent=AdkApp(app=app),
            config=deployment_config,
        )
    resource_name = deployed.api_resource.name
    resource_id = resource_name.rsplit("/", 1)[-1]
    print(f"Agent Runtime: {resource_name}")
    print("Add these values to .env:")
    print(f"GOOGLE_CLOUD_AGENT_ENGINE_ID={resource_id}")
    print(f"AGENT_PLATFORM_SESSIONS_ID={resource_id}")
    print(f"AGENT_PLATFORM_MEMORY_BANK_ID={resource_id}")


if __name__ == "__main__":
    main()
