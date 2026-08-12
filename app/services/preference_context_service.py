from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any

from app.preferences.memory_service import LongTermPreferenceService
from app.preferences.models import EffectivePreferenceContext, Preference, PreferenceSource
from app.preferences.profile_service import ProfilePreferenceService
from app.preferences.resolver import PreferenceResolver
from app.preferences.session_preferences import SessionPreferenceStore, normalize_session_state

logger = logging.getLogger(__name__)


class PreferenceContextService:
    def __init__(
        self,
        *,
        profile_service: ProfilePreferenceService,
        memory_service: LongTermPreferenceService,
        session_store: SessionPreferenceStore | None,
        resolver: PreferenceResolver,
        defaults: Sequence[Preference] = (),
    ) -> None:
        self.profile_service = profile_service
        self.memory_service = memory_service
        self.session_store = session_store
        self.resolver = resolver
        self.defaults = tuple(defaults)

    async def build_context(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        domain: str,
        *,
        session_state: Mapping[str, Any] | None = None,
    ) -> EffectivePreferenceContext:
        warnings: list[str] = []

        async def timed(label: str, awaitable: Any) -> Any:
            started = time.perf_counter()
            try:
                result = await awaitable
                logger.info(
                    "preference_source_loaded",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "preference_source": label,
                        "preference_count": len(result),
                        "lookup_duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                )
                return result
            # Source adapters cross network and SDK boundaries. Degrading one source is
            # deliberate; resolver validation errors occur after this block and still fail.
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "preference_source_unavailable",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "preference_source": label,
                        "error_type": type(exc).__name__,
                    },
                )
                warnings.append(f"{label} unavailable")
                return []

        profile_task = timed(
            "explicit_profile", self.profile_service.get_preferences(user_id, domain)
        )
        memory_task = timed(
            "long_term_memory", self.memory_service.retrieve_preferences(user_id, agent_id, domain)
        )
        if session_state is not None:
            session_preferences = normalize_session_state(session_state, domain)
            profile_preferences, memory_preferences = await asyncio.gather(
                profile_task, memory_task
            )
        else:
            session_task = (
                timed(
                    "session",
                    self.session_store.get_preferences(user_id, session_id, agent_id, domain),
                )
                if self.session_store
                else asyncio.sleep(0, result=[])
            )
            profile_preferences, memory_preferences, session_preferences = await asyncio.gather(
                profile_task, memory_task, session_task
            )
        context = self.resolver.resolve(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            domain=domain,
            session_preferences=session_preferences,
            explicit_profile_preferences=profile_preferences,
            long_term_preferences=memory_preferences,
            defaults=[p for p in self.defaults if p.source is PreferenceSource.DEFAULT],
            warnings=tuple(warnings),
        )
        logger.info(
            "preferences_resolved",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "preference_count": len(context.preferences),
                "preference_sources": sorted(
                    {p.source.value for p in context.preferences.values()}
                ),
            },
        )
        return context
