"""Uvicorn entry point for the independently owned Control Plane API."""

from control_plane_api.application import create_app

app = create_app()
