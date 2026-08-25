from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from memory_api.domain.memory import MemoryScope


@dataclass(frozen=True, slots=True)
class ScopeContract:
    name: str
    keys: tuple[str, ...]


class ScopeRegistry:
    """Validates provider scopes before a store can read or write memory."""

    def __init__(self, contracts: tuple[ScopeContract, ...] | None = None) -> None:
        configured = contracts or (
            ScopeContract("organization-user-profile", ("organization_id", "user_id")),
        )
        self._contracts = {contract.name: contract for contract in configured}

    def resolve(self, name: str, values: Mapping[str, str]) -> MemoryScope:
        contract = self._contracts.get(name)
        if contract is None:
            raise KeyError(f"unknown scope contract {name!r}")
        supplied = set(values)
        expected = set(contract.keys)
        if supplied != expected:
            missing = sorted(expected - supplied)
            unexpected = sorted(supplied - expected)
            raise ValueError(f"invalid scope keys; missing={missing}, unexpected={unexpected}")
        return MemoryScope(
            organization_id=values["organization_id"],
            user_id=values["user_id"],
        )
