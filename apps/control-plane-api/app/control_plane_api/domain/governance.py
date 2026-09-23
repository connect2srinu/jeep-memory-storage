"""Platform guardrails for memory governance.

The retention maximums are placeholders pending Kroger Privacy/Legal review (design doc
"Open items"); schema owners choose retention within them.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

# Maximum schema retention (days) per sensitivity tier. Health attributes count as "sensitive";
# restricted content is never stored, so it has no entry.
MAX_RETENTION_DAYS = {"normal": 1095, "sensitive": 730}

# A proposed member the user never confirmed is expired by the retention sweep after this long.
PROVISIONAL_MEMBER_TTL = timedelta(days=60)

# An unanswered health-data confirmation prompt stops being redeemable after this long.
PENDING_CONSENT_TTL = timedelta(hours=24)

# Purposes an agent may declare. Advertising is never allowed for per-member (possibly minor) or
# health data, whatever a schema declares.
PURPOSES = ("personalization", "analytics", "advertising")
RESTRICTED_PURPOSE = "advertising"
DEFAULT_ALLOWED_PURPOSES = ("personalization",)


_TIER_ORDER = {"normal": 0, "sensitive": 1, "restricted": 2}


def retention_tier(sensitivities: Iterable[str], *, health: bool) -> str:
    """The retention tier of a schema: its most sensitive attribute (health counts as sensitive)."""
    tier = "sensitive" if health else "normal"
    for value in sensitivities:
        if _TIER_ORDER.get(value, 0) > _TIER_ORDER[tier]:
            tier = value
    return "sensitive" if tier == "restricted" else tier


def check_retention(retention_days: int | None, tier: str, *, schema_id: str) -> None:
    """Reject a schema retention above the platform limit for its tier."""
    limit = MAX_RETENTION_DAYS[tier]
    if retention_days is not None and retention_days > limit:
        raise ValueError(
            f"retention of {retention_days} days for schema {schema_id!r} exceeds the platform "
            f"limit of {limit} days for {tier} data"
        )
