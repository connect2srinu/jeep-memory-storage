from __future__ import annotations

from app.config import settings


def main() -> None:
    import agentplatform

    if not settings.project or not settings.memory_resource_id:
        raise SystemExit("Configure project and Memory Bank ID")
    client = agentplatform.Client(project=settings.project, location=settings.location)
    name = f"projects/{settings.project}/locations/{settings.location}/reasoningEngines/{settings.memory_resource_id}"
    scope = {"user_id": "user-123", "app_name": settings.app_name, "domain": settings.domain}
    for item in client.agent_engines.memories.retrieve(name=name, scope=scope):
        print(item)


if __name__ == "__main__":
    main()
