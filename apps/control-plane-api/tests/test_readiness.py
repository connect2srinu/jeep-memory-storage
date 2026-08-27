from __future__ import annotations

import pytest
from control_plane_api.persistence import readiness
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
async def test_wait_for_database_retries_transient_resolution_failure(monkeypatch) -> None:
    calls = 0

    async def probe(_database_url: str) -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary DNS failure")

    monkeypatch.setattr(readiness, "probe_database", probe)

    successful_attempt = await readiness.wait_for_database(
        "postgresql+asyncpg://example.invalid/database",
        attempts=3,
        delay_seconds=0,
    )

    assert successful_attempt == 3
    assert calls == 3


@pytest.mark.asyncio
async def test_wait_for_database_fails_after_bounded_attempts(monkeypatch) -> None:
    async def probe(_database_url: str) -> None:
        raise OperationalError("SELECT 1", {}, OSError("connection refused"))

    monkeypatch.setattr(readiness, "probe_database", probe)

    with pytest.raises(readiness.DatabaseReadinessError, match="after 2 attempts"):
        await readiness.wait_for_database(
            "postgresql+asyncpg://example.invalid/database",
            attempts=2,
            delay_seconds=0,
        )


@pytest.mark.asyncio
async def test_wait_for_database_validates_retry_configuration() -> None:
    with pytest.raises(ValueError, match="attempts"):
        await readiness.wait_for_database("sqlite+aiosqlite://", attempts=0)
