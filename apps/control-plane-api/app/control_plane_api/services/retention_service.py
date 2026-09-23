"""Retention sweep: expire canonical values past their schema's retention, unconfirmed proposed
members, and unanswered health-data confirmation prompts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.domain.governance import PENDING_CONSENT_TTL, PROVISIONAL_MEMBER_TTL
from control_plane_api.observability.runtime import correlation_id_context
from control_plane_api.persistence.models import (
    AuditEventRecord,
    ConsentRecord,
    HouseholdMemberRecord,
    MemoryDomainRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
)
from control_plane_api.repositories import MemoryStore
from control_plane_api.security.admin import AdminAuthorizer, AdminPrincipal


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class RetentionService:
    def __init__(self, session: AsyncSession, store: MemoryStore) -> None:
        self.session = session
        self.store = store
        self.authorizer = AdminAuthorizer()

    async def sweep(
        self,
        principal: AdminPrincipal,
        organization_id: str,
        *,
        dry_run: bool = True,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Apply retention for one organization. ``dry_run`` previews; ``as_of`` previews what
        would expire at a later date and is only allowed with ``dry_run``."""
        self.authorizer.require_platform(principal)
        if as_of is not None and not dry_run:
            raise ValueError("asOf is only allowed for a dry-run preview")
        effective = _utc(as_of) if as_of else datetime.now(UTC)

        schemas: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        rows = await self.session.execute(
            select(ProfileSchemaVersionRecord, ProfileSchemaRecord)
            .join(ProfileSchemaRecord, ProfileSchemaRecord.id == ProfileSchemaVersionRecord.schema_id)
            .join(MemoryDomainRecord, MemoryDomainRecord.id == ProfileSchemaRecord.domain_id)
            .where(
                MemoryDomainRecord.organization_id == organization_id,
                ProfileSchemaVersionRecord.status == "ACTIVE",
                ProfileSchemaVersionRecord.retention_days.is_not(None),
            )
            .order_by(ProfileSchemaRecord.id)
        )
        for version, schema in rows.all():
            cutoff = effective - timedelta(days=version.retention_days)
            matches = await self.store.purge(
                organization_id=organization_id,
                schema_id=schema.id,
                older_than=cutoff,
                dry_run=dry_run,
            )
            schemas.append(
                {
                    "schemaId": schema.id,
                    "retentionDays": version.retention_days,
                    "cutoff": cutoff.isoformat(),
                    "matched": len(matches),
                }
            )
            entries.extend(matches)

        member_cutoff = effective - PROVISIONAL_MEMBER_TTL
        provisional = [
            record
            for record in await self.session.scalars(
                select(HouseholdMemberRecord).where(
                    HouseholdMemberRecord.organization_id == organization_id,
                    HouseholdMemberRecord.status == "provisional",
                )
            )
            if _utc(record.created_at) < member_cutoff
        ]
        consent_cutoff = effective - PENDING_CONSENT_TTL
        pending = [
            record
            for record in await self.session.scalars(
                select(ConsentRecord).where(
                    ConsentRecord.organization_id == organization_id,
                    ConsentRecord.status == "PENDING",
                )
            )
            if _utc(record.requested_at) < consent_cutoff
        ]
        if not dry_run:
            for record in provisional:
                record.status = "expired"
            for record in pending:
                record.status = "EXPIRED"
            self.session.add(
                AuditEventRecord(
                    id=str(uuid4()),
                    actor=principal.principal,
                    action="retention.swept",
                    target_type="organization",
                    target_id=organization_id,
                    correlation_id=correlation_id_context.get() or str(uuid4()),
                    before_metadata=None,
                    after_metadata={
                        "values_deleted": len(entries),
                        "provisional_members_expired": len(provisional),
                        "pending_consents_expired": len(pending),
                    },
                )
            )
            await self.session.flush()
        return {
            "dryRun": dry_run,
            "asOf": effective.isoformat(),
            "schemas": schemas,
            "valuesMatched": len(entries),
            "entries": entries,
            "provisionalMembers": [
                {
                    "householdId": record.household_id,
                    "memberId": record.member_id,
                    "displayName": record.display_name,
                }
                for record in provisional
            ],
            "pendingConsents": len(pending),
        }
