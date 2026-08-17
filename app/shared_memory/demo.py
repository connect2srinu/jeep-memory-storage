from __future__ import annotations

from datetime import UTC, datetime

from app.shared_memory.adapters import (
    InMemoryLongTermMemoryAdapter,
    InMemorySessionAdapter,
    MockProfileAdapter,
    NullMemoryProfileAdapter,
)
from app.shared_memory.auth import AuthorizationService
from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import (
    EffectivePreferenceContext,
    Preference,
    PreferenceScope,
    PreferenceSource,
)
from app.shared_memory.policies import PreferencePolicyRegistry
from app.shared_memory.resolver import PreferenceResolver
from app.shared_memory.services import (
    InMemoryCandidateRepository,
    InMemorySnapshotService,
    LongTermMemoryService,
    PreferenceContextService,
    ProfilePreferenceService,
    SessionContextService,
    SharedMemoryPlatformService,
)


async def build_final_validation_context() -> EffectivePreferenceContext:
    catalog = PreferenceCatalog.default()
    policies = PreferencePolicyRegistry.default(0.7)
    authorization = AuthorizationService(policies)
    resolver = PreferenceResolver(catalog, policies)
    session_backend = InMemorySessionAdapter()
    dynamic_memory = Preference(
        key="grocery.banana_ripeness",
        value="slightly_green",
        source=PreferenceSource.DYNAMIC_MEMORY,
        owner_domain="grocery",
        scope=PreferenceScope.LONG_TERM,
        confidence=0.94,
        updated_at=datetime.now(UTC),
        canonical=False,
        provenance={"service": "demo-memory-bank", "memory_name": "banana-ripeness"},
    )
    memory_backend = InMemoryLongTermMemoryAdapter(
        [("U123", "shared-memory-platform", dynamic_memory)]
    )
    long_term_service = LongTermMemoryService(memory_backend, NullMemoryProfileAdapter())
    session_service = SessionContextService(session_backend)
    snapshot = InMemorySnapshotService()
    context_service = PreferenceContextService(
        session_service=session_service,
        profile_service=ProfilePreferenceService((MockProfileAdapter(catalog),)),
        long_term_service=long_term_service,
        catalog=catalog,
        policies=policies,
        authorization=authorization,
        resolver=resolver,
        snapshot_service=snapshot,
        app_name="shared-memory-platform",
    )
    platform = SharedMemoryPlatformService(
        context_service=context_service,
        session_service=session_service,
        long_term_service=long_term_service,
        catalog=catalog,
        authorization=authorization,
        snapshot_service=snapshot,
        candidate_repository=InMemoryCandidateRepository(),
        app_name="shared-memory-platform",
    )
    await session_backend.save_session_preference(
        "U123",
        "S456",
        Preference(
            key="grocery.allow_substitutions",
            value=True,
            source=PreferenceSource.SESSION_OVERRIDE,
            owner_domain="grocery",
            scope=PreferenceScope.SESSION,
            confidence=1.0,
            updated_at=datetime.now(UTC),
            canonical=True,
            provenance={"service": "demo-session"},
        ),
    )
    return await platform.get_effective_context(
        user_id="U123",
        session_id="S456",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        use_snapshot=False,
    )
