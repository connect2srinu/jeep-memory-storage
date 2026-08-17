from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from dataclasses import replace
from typing import Any

from app.shared_memory.auth import AuthorizationService, ConsumerCapability
from app.shared_memory.catalog import PreferenceCatalog, PreferenceValidationError
from app.shared_memory.models import EffectivePreferenceContext, Preference
from app.shared_memory.observability import log_event
from app.shared_memory.policies import PreferencePolicyRegistry
from app.shared_memory.resolver import PreferenceResolver
from app.shared_memory.services.long_term_memory_service import LongTermMemoryService
from app.shared_memory.services.profile_preference_service import ProfilePreferenceService
from app.shared_memory.services.session_context_service import SessionContextService
from app.shared_memory.services.snapshot_service import (
    EffectivePreferenceSnapshotService,
    SnapshotKey,
)

logger = logging.getLogger(__name__)


class PreferenceContextService:
    """Platform orchestration layer; consuming agents never query sources directly."""

    def __init__(
        self,
        *,
        session_service: SessionContextService,
        profile_service: ProfilePreferenceService,
        long_term_service: LongTermMemoryService,
        catalog: PreferenceCatalog,
        policies: PreferencePolicyRegistry,
        authorization: AuthorizationService,
        resolver: PreferenceResolver,
        snapshot_service: EffectivePreferenceSnapshotService,
        app_name: str,
        defaults: tuple[Preference, ...] = (),
    ) -> None:
        self.session_service = session_service
        self.profile_service = profile_service
        self.long_term_service = long_term_service
        self.catalog = catalog
        self.policies = policies
        self.authorization = authorization
        self.resolver = resolver
        self.snapshot_service = snapshot_service
        self.app_name = app_name
        self.defaults = defaults

    async def build_effective_context(
        self,
        user_id: str,
        session_id: str,
        consumer_domain: str,
        agent_id: str,
        *,
        context: dict[str, Any] | None = None,
        use_snapshot: bool = True,
    ) -> EffectivePreferenceContext:
        started = time.perf_counter()
        self.authorization.authenticate(user_id, agent_id)
        self.authorization.authorize_consumer(
            agent_id, consumer_domain, ConsumerCapability.RESOLVE_CONTEXT
        )
        readable_domains = self.authorization.readable_domains(consumer_domain)
        if consumer_domain not in readable_domains:
            raise PermissionError("consumer domain cannot read its own preferences")

        snapshot_key = SnapshotKey.create(
            user_id=user_id,
            consumer_domain=consumer_domain,
            context={"session_id": session_id, "agent_id": agent_id, **(context or {})},
            catalog_version=self.catalog.version,
            policy_version=self.policies.version,
        )
        if use_snapshot:
            cached = await self.snapshot_service.get(snapshot_key)
            if cached is not None:
                log_event(
                    "shared_memory_snapshot_hit",
                    user_id=user_id,
                    session_id=session_id,
                    consumer_domain=consumer_domain,
                    agent_id=agent_id,
                )
                return cached

        warnings: list[str] = []
        source_metrics: dict[str, dict[str, object]] = {}

        async def load(label: str, request: Awaitable[list[Preference]]) -> list[Preference]:
            source_started = time.perf_counter()
            try:
                values = await request
                source_metrics[label] = {
                    "count": len(values),
                    "latency_ms": round((time.perf_counter() - source_started) * 1000, 2),
                }
                return values
            except Exception as exc:  # noqa: BLE001 - remote-source degradation boundary
                warnings.append(f"{label} unavailable")
                source_metrics[label] = {
                    "count": 0,
                    "latency_ms": round((time.perf_counter() - source_started) * 1000, 2),
                    "error_type": type(exc).__name__,
                }
                return []

        session_values, profile_values, memory_profile_values, dynamic_values = await asyncio.gather(
            load(
                "session",
                self.session_service.get_session_preferences(
                    user_id, session_id, readable_domains
                ),
            ),
            load(
                "explicit_profile",
                self.profile_service.get_preferences(user_id, readable_domains),
            ),
            load(
                "memory_profile",
                self.long_term_service.get_memory_profile_preferences(
                    user_id, self.app_name, readable_domains
                ),
            ),
            load(
                "dynamic_memory",
                self.long_term_service.get_dynamic_preferences(
                    user_id, self.app_name, readable_domains
                ),
            ),
        )

        normalized: list[Preference] = []
        filtered = 0
        for preference in [
            *self.defaults,
            *session_values,
            *profile_values,
            *memory_profile_values,
            *dynamic_values,
        ]:
            entry = self.catalog.lookup(preference.key, preference.owner_domain)
            if not self.authorization.can_read(
                consumer_domain, preference.owner_domain, entry
            ).allowed:
                filtered += 1
                continue
            try:
                self.catalog.validate_value(entry, preference.value)
            except PreferenceValidationError:
                filtered += 1
                warnings.append(f"invalid preference ignored: {preference.key}")
                continue
            normalized.append(preference)

        resolved = self.resolver.resolve(
            user_id=user_id,
            session_id=session_id,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
            preferences=normalized,
            readable_domains=readable_domains,
            warnings=tuple(warnings),
        )
        if not self.authorization.consumers.allows(
            agent_id, consumer_domain, ConsumerCapability.INSPECT_PROVENANCE
        ):
            resolved = replace(
                resolved,
                preferences={
                    key: replace(
                        item,
                        preference=replace(item.preference, provenance={}),
                    )
                    for key, item in resolved.preferences.items()
                },
            )
        version = await self.snapshot_service.put(snapshot_key, resolved)
        resolved = replace(resolved, snapshot_version=version)
        log_event(
            "shared_memory_context_resolved",
            user_id=user_id,
            session_id=session_id,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
            source_systems=source_metrics,
            retrieved_count=len(normalized),
            filtered_count=filtered,
            result_count=len(resolved.preferences),
            resolver_policy_version=self.policies.version,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            cache="miss",
            authorization="allowed",
        )
        return resolved
