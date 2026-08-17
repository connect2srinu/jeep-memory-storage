from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.shared_memory.auth import AuthorizationService, ConsumerCapability
from app.shared_memory.catalog import PreferenceCatalog, PreferenceValidationError
from app.shared_memory.models import (
    CandidateDisposition,
    EffectivePreferenceContext,
    Preference,
    PreferenceCandidate,
    PreferenceScope,
    PreferenceSource,
    SubmissionResult,
)
from app.shared_memory.observability import log_event
from app.shared_memory.services.long_term_memory_service import LongTermMemoryService
from app.shared_memory.services.preference_context_service import PreferenceContextService
from app.shared_memory.services.session_context_service import SessionContextService
from app.shared_memory.services.snapshot_service import EffectivePreferenceSnapshotService


@dataclass(slots=True)
class InMemoryCandidateRepository:
    """POC candidate queue extension point; replace with an auditable workflow store."""

    items: list[PreferenceCandidate]

    def __init__(self) -> None:
        self.items = []

    async def add(self, candidate: PreferenceCandidate) -> str:
        self.items.append(candidate)
        return f"candidate-{len(self.items)}"


class SharedMemoryPlatformService:
    """Stable service facade consumed by APIs and business agents."""

    def __init__(
        self,
        *,
        context_service: PreferenceContextService,
        session_service: SessionContextService,
        long_term_service: LongTermMemoryService,
        catalog: PreferenceCatalog,
        authorization: AuthorizationService,
        snapshot_service: EffectivePreferenceSnapshotService,
        candidate_repository: InMemoryCandidateRepository,
        app_name: str,
    ) -> None:
        self.context_service = context_service
        self.session_service = session_service
        self.long_term_service = long_term_service
        self.catalog = catalog
        self.authorization = authorization
        self.snapshot_service = snapshot_service
        self.candidate_repository = candidate_repository
        self.app_name = app_name

    async def get_effective_context(
        self,
        *,
        user_id: str,
        session_id: str,
        consumer_domain: str,
        agent_id: str,
        context: dict[str, object] | None = None,
        use_snapshot: bool = True,
    ) -> EffectivePreferenceContext:
        return await self.context_service.build_effective_context(
            user_id,
            session_id,
            consumer_domain,
            agent_id,
            context=dict(context or {}),
            use_snapshot=use_snapshot,
        )

    async def submit_preference(
        self,
        *,
        candidate: PreferenceCandidate,
        consumer_domain: str,
        agent_id: str,
    ) -> SubmissionResult:
        self.authorization.authenticate(candidate.user_id, agent_id)
        self.authorization.authorize_consumer(
            agent_id, consumer_domain, ConsumerCapability.SUBMIT_CANDIDATES
        )
        canonical_key, owner_domain, canonical = self.catalog.canonicalize(
            candidate.key, candidate.proposed_domain
        )
        entry = self.catalog.lookup(canonical_key, owner_domain)
        try:
            value = self.catalog.validate_value(entry, candidate.value)
            self.catalog.validate_scope(entry, candidate.requested_scope)
        except PreferenceValidationError as exc:
            return SubmissionResult(
                CandidateDisposition.REJECTED,
                candidate,
                canonical_key,
                owner_domain,
                str(exc),
            )

        decision = self.authorization.can_write(consumer_domain, owner_domain, entry)
        log_event(
            "shared_memory_authorization_decision",
            user_id=candidate.user_id,
            session_id=candidate.session_id,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
            owner_domain=owner_domain,
            action="write",
            allowed=decision.allowed,
            reason=decision.reason,
        )
        if not decision.allowed:
            reference = await self.candidate_repository.add(candidate)
            return SubmissionResult(
                CandidateDisposition.CROSS_DOMAIN_CANDIDATE,
                candidate,
                canonical_key,
                owner_domain,
                "Candidate recorded for owner-domain validation; no preference was written.",
                reference,
            )

        now = datetime.now(UTC)
        expires_at = (
            now + timedelta(seconds=entry.ttl_seconds)
            if entry and entry.ttl_seconds and candidate.requested_scope is PreferenceScope.SESSION
            else None
        )
        preference = Preference(
            key=canonical_key,
            value=value,
            source=(
                PreferenceSource.SESSION_OVERRIDE
                if candidate.requested_scope is PreferenceScope.SESSION
                else PreferenceSource.DOMAIN_MEMORY
                if canonical
                else PreferenceSource.DYNAMIC_MEMORY
            ),
            owner_domain=owner_domain,
            scope=candidate.requested_scope,
            confidence=candidate.confidence,
            updated_at=now,
            expires_at=expires_at,
            confirmed=candidate.explicit,
            canonical=canonical,
            schema_version=entry.schema_version if entry else "1",
            sensitivity=entry.sensitivity if entry else "normal",
            provenance={
                "service": "shared-memory-platform",
                "source": candidate.source,
                "evidence": candidate.evidence,
            },
        )
        if candidate.requested_scope is PreferenceScope.SESSION:
            await self.session_service.save_session_preference(
                candidate.user_id, candidate.session_id, preference
            )
            await self.snapshot_service.invalidate(candidate.user_id)
            return SubmissionResult(
                CandidateDisposition.STORED_IN_SESSION,
                candidate,
                canonical_key,
                owner_domain,
                "Preference stored only in structured session state.",
            )

        try:
            reference = await self.long_term_service.store_dynamic_preference(
                candidate.user_id, self.app_name, preference
            )
        except Exception as exc:  # noqa: BLE001 - storage boundary returns explicit status
            return SubmissionResult(
                CandidateDisposition.NOT_PERSISTED,
                candidate,
                canonical_key,
                owner_domain,
                f"Long-term preference was validated but not persisted ({type(exc).__name__}).",
            )
        await self.snapshot_service.invalidate(candidate.user_id)
        return SubmissionResult(
            CandidateDisposition.STORED_IN_DYNAMIC_MEMORY,
            candidate,
            canonical_key,
            owner_domain,
            "Preference stored in domain-scoped Memory Bank memory.",
            reference,
        )
