from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from .database import normalize_database_url


class DatabaseReadinessError(RuntimeError):
    """Raised when the database does not become reachable within the retry budget."""


async def probe_database(database_url: str) -> None:
    """Open a fresh connection and execute a provider-neutral readiness query."""
    engine = create_async_engine(normalize_database_url(database_url))
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def wait_for_database(
    database_url: str,
    *,
    attempts: int = 30,
    delay_seconds: float = 2.0,
) -> int:
    """Wait for DNS and database connectivity, returning the successful attempt number."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must not be negative")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await probe_database(database_url)
            return attempt
        except (OSError, SQLAlchemyError) as error:
            last_error = error
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)

    raise DatabaseReadinessError(
        f"database did not become ready after {attempts} attempts"
    ) from last_error
