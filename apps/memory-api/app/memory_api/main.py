"""Independent Memory API entry point for the first migration slice."""

from app.api import api as app


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "application": "memory-api"}
