from __future__ import annotations

from urllib.parse import urlparse

from app.agent import app
from app.config import settings

DISPLAY_NAME = "grocery-shared-preferences-poc"
REQUIREMENTS = [
    "google-adk[gcp]>=2.0.0,<3.0.0",
    "google-cloud-aiplatform[agent_engines,adk]>=1.112.0,<3.0.0",
    "python-dotenv>=1.0.1,<2.0.0",
]


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
