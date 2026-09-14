from __future__ import annotations

from enum import StrEnum


class SensitivityTier(StrEnum):
    """How sensitive a memory's content is. Values match the catalog classification strings."""

    NON_SENSITIVE = "normal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class MemorySource(StrEnum):
    """Whether a memory was explicitly directed by the user or inferred by the agent."""

    USER_DIRECTED = "user_directed"
    INFERENCE = "inference"


_TIER_ORDER = {
    SensitivityTier.NON_SENSITIVE: 0,
    SensitivityTier.SENSITIVE: 1,
    SensitivityTier.RESTRICTED: 2,
}


def parse_tier(value: str | None) -> SensitivityTier:
    if not value:
        return SensitivityTier.NON_SENSITIVE
    try:
        return SensitivityTier(value)
    except ValueError:
        return SensitivityTier.NON_SENSITIVE


def max_tier(left: SensitivityTier, right: SensitivityTier) -> SensitivityTier:
    return left if _TIER_ORDER[left] >= _TIER_ORDER[right] else right
