from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files


class ConsumerCapability(StrEnum):
    RESOLVE_CONTEXT = "resolve_context"
    SUBMIT_CANDIDATES = "submit_candidates"
    INSPECT_PROVENANCE = "inspect_provenance"
    ADMINISTER_MEMORY = "administer_memory"


@dataclass(frozen=True, slots=True)
class ConsumerRegistration:
    agent_id: str
    consumer_domain: str
    service_account: str | None
    required_preferences: tuple[str, ...]
    capabilities: frozenset[ConsumerCapability]


class ConsumerRegistry:
    """Generated operation-level authorization for registered agent consumers."""

    def __init__(self, registrations: dict[str, ConsumerRegistration]) -> None:
        self.registrations = registrations

    @classmethod
    def default(cls) -> ConsumerRegistry:
        path = files("app.shared_memory.contracts").joinpath("consumers.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        registrations = {}
        for agent_id, item in payload["consumers"].items():
            capabilities = frozenset(
                ConsumerCapability(name)
                for name, enabled in item.get("capabilities", {}).items()
                if enabled
            )
            registrations[agent_id] = ConsumerRegistration(
                agent_id=agent_id,
                consumer_domain=item["consumer_domain"],
                service_account=item.get("service_account"),
                required_preferences=tuple(item.get("required_preferences", [])),
                capabilities=capabilities,
            )
        return cls(registrations)

    def require(
        self, agent_id: str, consumer_domain: str, capability: ConsumerCapability
    ) -> ConsumerRegistration:
        registration = self.registrations.get(agent_id)
        if registration is None:
            raise PermissionError(f"agent {agent_id!r} is not registered")
        if registration.consumer_domain != consumer_domain:
            raise PermissionError("registered agent domain does not match consumer domain")
        if capability not in registration.capabilities:
            raise PermissionError(
                f"agent {agent_id!r} lacks capability {capability.value}"
            )
        return registration

    def allows(
        self, agent_id: str, consumer_domain: str, capability: ConsumerCapability
    ) -> bool:
        try:
            self.require(agent_id, consumer_domain, capability)
        except PermissionError:
            return False
        return True
