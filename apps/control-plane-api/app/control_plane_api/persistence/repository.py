from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.domain import LifecycleStatus, MemoryDomain

from .models import MemoryDomainRecord


class ControlPlaneRepository(Protocol):
    async def get_domain(self, domain_id: str) -> MemoryDomain | None: ...

    async def list_domains(self) -> tuple[MemoryDomain, ...]: ...


class SqlAlchemyControlPlaneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _domain(record: MemoryDomainRecord) -> MemoryDomain:
        return MemoryDomain(
            id=record.id,
            name=record.name,
            description=record.description,
            owner_team=record.owner_team,
            owner_contact=record.owner_contact,
            status=LifecycleStatus(record.status),
        )

    async def get_domain(self, domain_id: str) -> MemoryDomain | None:
        record = await self.session.get(MemoryDomainRecord, domain_id)
        return self._domain(record) if record else None

    async def list_domains(self) -> tuple[MemoryDomain, ...]:
        result = await self.session.scalars(
            select(MemoryDomainRecord).order_by(MemoryDomainRecord.id)
        )
        return tuple(self._domain(record) for record in result)
