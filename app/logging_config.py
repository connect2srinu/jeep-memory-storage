from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    _FIELDS = (
        "user_id_hash",
        "session_id",
        "agent_id",
        "consumer_domain",
        "owner_domain",
        "action",
        "allowed",
        "reason",
        "source_systems",
        "retrieved_count",
        "filtered_count",
        "result_count",
        "resolver_policy_version",
        "latency_ms",
        "cache",
        "authorization",
        "preference_source",
        "preference_count",
        "preference_sources",
        "lookup_duration_ms",
        "error_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update({key: getattr(record, key) for key in self._FIELDS if hasattr(record, key)})
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
