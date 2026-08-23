"""Uvicorn entry point for the independently owned Memory API."""

from memory_api.application import create_app

app = create_app()
