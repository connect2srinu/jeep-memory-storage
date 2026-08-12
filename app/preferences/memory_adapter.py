from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from .models import Preference, PreferenceSource

_PATTERNS = (
    re.compile(
        r"(?:I|user) (?:always )?prefer(?:s)? (?P<value>.+?) for (?P<key>[a-z_ ]+)$", re.IGNORECASE
    ),
    re.compile(r"(?P<key>[a-z_ ]+)\s*(?:is|=)\s*(?P<value>.+)$", re.IGNORECASE),
)


class MemoryPreferenceAdapter:
    """Transforms Memory Bank facts; it never applies precedence."""

    def adapt(self, retrieved: Any, domain: str) -> Preference | None:
        memory = getattr(retrieved, "memory", retrieved)
        fact = getattr(memory, "fact", None)
        if not isinstance(fact, str):
            return None
        name = getattr(memory, "name", "unknown")
        updated_at = getattr(memory, "update_time", None)
        confidence = self._confidence_from_distance(getattr(retrieved, "distance", None))
        parsed = self._parse_fact(fact)
        if parsed is None or parsed.get("domain", domain) != domain:
            return None
        return Preference(
            key=str(parsed["key"]),
            value=parsed["value"],
            source=PreferenceSource.LONG_TERM_MEMORY,
            domain=domain,
            confidence=float(parsed.get("confidence", confidence)),
            updated_at=updated_at if isinstance(updated_at, datetime) else None,
            provenance={"service": "agent-platform-memory-bank", "memory_name": name},
        )

    @staticmethod
    def encode_fact(preference: Preference) -> str:
        return json.dumps(
            {
                "schema": "shared-preference/v1",
                "domain": preference.domain,
                "key": preference.key,
                "value": preference.value,
                "confidence": preference.confidence,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _parse_fact(fact: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(fact)
            if isinstance(payload, dict) and "key" in payload and "value" in payload:
                return payload
        except json.JSONDecodeError:
            pass
        for pattern in _PATTERNS:
            match = pattern.fullmatch(fact.strip().rstrip("."))
            if match:
                value: Any = match.group("value").strip()
                if value.lower() in {"true", "yes"}:
                    value = True
                elif value.lower() in {"false", "no"}:
                    value = False
                return {"key": match.group("key").strip().replace(" ", "_"), "value": value}
        return None

    @staticmethod
    def _confidence_from_distance(distance: Any) -> float:
        if not isinstance(distance, (int, float)):
            return 0.8
        return max(0.0, min(1.0, 1.0 / (1.0 + float(distance))))
