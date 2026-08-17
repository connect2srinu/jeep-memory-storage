from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger("shared_memory")


def redact_identifier(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def log_event(event: str, **fields: Any) -> None:
    sanitized = dict(fields)
    if "user_id" in sanitized:
        sanitized["user_id_hash"] = redact_identifier(str(sanitized.pop("user_id")))
    logger.info(event, extra=sanitized)

