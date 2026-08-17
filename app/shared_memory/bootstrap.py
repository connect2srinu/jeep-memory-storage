from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.shared_memory.adapters import (
    AgentPlatformMemoryBankAdapter,
    AgentPlatformMemoryProfileAdapter,
    InMemorySessionAdapter,
    MockProfileAdapter,
    ToolContextSessionAdapter,
)
from app.shared_memory.auth import AuthorizationService
from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import Preference, PreferenceSource
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


@dataclass(slots=True)
class PlatformDependencies:
    catalog: PreferenceCatalog
    policies: PreferencePolicyRegistry
    authorization: AuthorizationService
    resolver: PreferenceResolver
    profile_service: ProfilePreferenceService
    long_term_service: LongTermMemoryService
    snapshot_service: InMemorySnapshotService
    candidate_repository: InMemoryCandidateRepository
    app_name: str

    @classmethod
    def from_environment(cls) -> PlatformDependencies:
        catalog = PreferenceCatalog.default()
        policies = PreferencePolicyRegistry.default(settings.minimum_memory_confidence)
        authorization = AuthorizationService(policies)
        resolver = PreferenceResolver(catalog, policies)
        profile_service = ProfilePreferenceService((MockProfileAdapter(catalog),))
        dynamic_backend = AgentPlatformMemoryBankAdapter(
            catalog,
            project=settings.project,
            location=settings.location,
            agent_engine_id=settings.memory_resource_id,
        )
        profile_backend = AgentPlatformMemoryProfileAdapter(
            catalog,
            project=settings.project,
            location=settings.location,
            agent_engine_id=settings.memory_resource_id,
        )
        return cls(
            catalog=catalog,
            policies=policies,
            authorization=authorization,
            resolver=resolver,
            profile_service=profile_service,
            long_term_service=LongTermMemoryService(dynamic_backend, profile_backend),
            snapshot_service=InMemorySnapshotService(),
            candidate_repository=InMemoryCandidateRepository(),
            app_name=settings.app_name,
        )

    def build_service(self, session_backend: Any) -> SharedMemoryPlatformService:
        session_service = SessionContextService(session_backend)
        defaults = (
            Preference(
                key="grocery.allow_substitutions",
                value=False,
                source=PreferenceSource.DEFAULT,
                owner_domain="grocery",
                updated_at=datetime.now(UTC),
                canonical=True,
                provenance={"service": "platform-defaults"},
            ),
            Preference(
                key="grocery.organic_preference",
                value=False,
                source=PreferenceSource.DEFAULT,
                owner_domain="grocery",
                updated_at=datetime.now(UTC),
                canonical=True,
                provenance={"service": "platform-defaults"},
            ),
        )
        context_service = PreferenceContextService(
            session_service=session_service,
            profile_service=self.profile_service,
            long_term_service=self.long_term_service,
            catalog=self.catalog,
            policies=self.policies,
            authorization=self.authorization,
            resolver=self.resolver,
            snapshot_service=self.snapshot_service,
            app_name=self.app_name,
            defaults=defaults,
        )
        return SharedMemoryPlatformService(
            context_service=context_service,
            session_service=session_service,
            long_term_service=self.long_term_service,
            catalog=self.catalog,
            authorization=self.authorization,
            snapshot_service=self.snapshot_service,
            candidate_repository=self.candidate_repository,
            app_name=self.app_name,
        )

    def for_tool_context(self, tool_context: Any) -> SharedMemoryPlatformService:
        return self.build_service(ToolContextSessionAdapter(tool_context))

    def for_local_api(self) -> SharedMemoryPlatformService:
        return self.build_service(InMemorySessionAdapter())


platform_dependencies = PlatformDependencies.from_environment()
