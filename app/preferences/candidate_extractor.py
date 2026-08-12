from __future__ import annotations

import re
from typing import Any

from .models import PreferenceCandidate, PreferenceScope

_RULES = (
    (
        re.compile(
            r"\b(?:for today|today|for this (?:trip|order))\b.*?\bsubstitutions? (?:are|is) (?:okay|ok|allowed)\b",
            re.IGNORECASE,
        ),
        "allow_substitutions",
        True,
        PreferenceScope.SESSION,
    ),
    (
        re.compile(
            r"\b(?:for today|today|for this trip)\b.*?\b(?:use|prefer) (?P<value>[a-z][a-z ]+?)(?:\.|$)",
            re.IGNORECASE,
        ),
        "preferred_milk",
        None,
        PreferenceScope.SESSION,
    ),
    (
        re.compile(
            r"\b(?:today|for this trip)\b.*?\b(?:do not|don't) apply my vegetarian preference\b",
            re.IGNORECASE,
        ),
        "diet",
        "none",
        PreferenceScope.SESSION,
    ),
    (
        re.compile(
            r"\b(?:for today|today|for this trip)\b.*?\b(?:under|below|budget (?:is|of)) \$(?P<value>\d+(?:\.\d{1,2})?)\b",
            re.IGNORECASE,
        ),
        "budget",
        None,
        PreferenceScope.SESSION,
    ),
    (
        re.compile(r"\bI always prefer (?P<value>[a-z][a-z ]+?)(?:\.|$)", re.IGNORECASE),
        "preferred_product",
        None,
        PreferenceScope.USER,
    ),
    (
        re.compile(r"\bI always prefer (?P<value>(?:oat|whole|almond|soy) milk)\b", re.IGNORECASE),
        "preferred_milk",
        None,
        PreferenceScope.USER,
    ),
    (
        re.compile(r"\bI always prefer organic produce\b", re.IGNORECASE),
        "organic",
        True,
        PreferenceScope.USER,
    ),
)


def extract_candidate(message: str, domain: str = "customer.grocery") -> PreferenceCandidate | None:
    """Small transparent POC extractor; replace with schema-validated Gemini extraction."""
    for pattern, key, fixed_value, scope in reversed(_RULES):
        match = pattern.search(message)
        if match:
            value: Any = fixed_value if fixed_value is not None else match.group("value").strip()
            if key == "budget":
                value = float(value)
            return PreferenceCandidate(
                key=key,
                value=value,
                requested_scope=scope,
                confidence=0.99,
                evidence="explicit temporal or durability phrase",
                source_message=message,
                domain=domain,
            )
    return None
