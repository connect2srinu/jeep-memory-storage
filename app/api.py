"""Uvicorn entry point for the Shared Memory Platform API."""

from app.shared_memory.api import create_api_app
from app.shared_memory.bootstrap import platform_dependencies

api = create_api_app(platform_dependencies.for_local_api())

