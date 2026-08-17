from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.shared_memory.models import EffectivePreferenceContext


@dataclass(frozen=True, slots=True)
class SnapshotKey:
    user_id: str
    consumer_domain: str
    context_hash: str
    catalog_version: str
    policy_version: str

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        consumer_domain: str,
        context: dict[str, Any],
        catalog_version: str,
        policy_version: str,
    ) -> SnapshotKey:
        encoded = json.dumps(context, sort_keys=True, default=str).encode()
        return cls(
            user_id,
            consumer_domain,
            hashlib.sha256(encoded).hexdigest()[:16],
            catalog_version,
            policy_version,
        )


class EffectivePreferenceSnapshotService(Protocol):
    async def get(self, key: SnapshotKey) -> EffectivePreferenceContext | None: ...

    async def put(self, key: SnapshotKey, value: EffectivePreferenceContext) -> str: ...

    async def invalidate(self, user_id: str, domain: str | None = None) -> None: ...


class InMemorySnapshotService:
    """Derived POC cache. It is never a preference source of truth."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[
            SnapshotKey, tuple[EffectivePreferenceContext, datetime, str]
        ] = {}
        self._version = 0

    async def get(self, key: SnapshotKey) -> EffectivePreferenceContext | None:
        item = self._items.get(key)
        if item is None:
            return None
        value, expires_at, _ = item
        if expires_at <= datetime.now(UTC):
            self._items.pop(key, None)
            return None
        return value

    async def put(self, key: SnapshotKey, value: EffectivePreferenceContext) -> str:
        self._version += 1
        version = str(self._version)
        stored = replace(value, snapshot_version=version)
        self._items[key] = (stored, datetime.now(UTC) + self.ttl, version)
        return version

    async def invalidate(self, user_id: str, domain: str | None = None) -> None:
        keys = [
            key
            for key in self._items
            if key.user_id == user_id and (domain is None or key.consumer_domain == domain)
        ]
        for key in keys:
            self._items.pop(key, None)
