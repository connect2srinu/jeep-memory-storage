from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.shared_memory.models import PreferenceCandidate, PreferenceScope


@dataclass(frozen=True, slots=True)
class _Rule:
    pattern: re.Pattern[str]
    key: str
    domain: str
    scope: PreferenceScope
    fixed_value: Any = None


_RULES = (
    _Rule(
        re.compile(
            r"^\s*substitutions? (?:are|is) (?:okay|ok|allowed)[.!]?\s*$",
            re.IGNORECASE,
        ),
        "grocery.allow_substitutions",
        "grocery",
        PreferenceScope.SESSION,
        True,
    ),
    _Rule(
        re.compile(
            r"\b(?:for today|today|for this (?:trip|order))\b.*?"
            r"\bsubstitutions? (?:are|is) (?:okay|ok|allowed)\b",
            re.IGNORECASE,
        ),
        "grocery.allow_substitutions",
        "grocery",
        PreferenceScope.SESSION,
        True,
    ),
    _Rule(
        re.compile(
            r"\b(?:for today|today|for this trip)\b.*?\b(?:use|prefer) "
            r"(?P<value>(?:oat|whole|almond|soy) milk)\b",
            re.IGNORECASE,
        ),
        "grocery.preferred_milk",
        "grocery",
        PreferenceScope.SESSION,
    ),
    _Rule(
        re.compile(
            r"\b(?:for today|today|for this (?:trip|order))\b.*?"
            r"\b(?:use|prefer) (?P<value>[a-z][a-z0-9 -]*?) as (?:my )?snack\b",
            re.IGNORECASE,
        ),
        "grocery.preferred_snack",
        "grocery",
        PreferenceScope.SESSION,
    ),
    _Rule(
        re.compile(
            r"\b(?:for today|today|for this (?:trip|order))\b.*?"
            r"\bmy preferred snack is (?P<value>[a-z][a-z0-9 -]*?)(?:[.!]|$)",
            re.IGNORECASE,
        ),
        "grocery.preferred_snack",
        "grocery",
        PreferenceScope.SESSION,
    ),
    _Rule(
        re.compile(
            r"\b(?:today|for this trip)\b.*?\b(?:do not|don't) "
            r"apply my vegetarian preference\b",
            re.IGNORECASE,
        ),
        "grocery.diet_override",
        "grocery",
        PreferenceScope.SESSION,
        "none",
    ),
    _Rule(
        re.compile(
            r"\b(?:for today|today|for this trip)\b.*?"
            r"\b(?:under|below|budget (?:is|of)) \$(?P<value>\d+(?:\.\d{1,2})?)\b",
            re.IGNORECASE,
        ),
        "grocery.budget",
        "grocery",
        PreferenceScope.SESSION,
    ),
    _Rule(
        re.compile(r"\bI always prefer organic produce\b", re.IGNORECASE),
        "grocery.organic_preference",
        "grocery",
        PreferenceScope.LONG_TERM,
        True,
    ),
    _Rule(
        re.compile(
            r"\bI always prefer (?P<value>(?:oat|whole|almond|soy) milk)\b",
            re.IGNORECASE,
        ),
        "grocery.preferred_milk",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\bI (?:always|usually) prefer (?P<value>[a-z][a-z0-9 -]*?) "
            r"as (?:my )?snack\b",
            re.IGNORECASE,
        ),
        "grocery.preferred_snack",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\bI confirm that (?:my )?preferred snack is "
            r"(?P<value>[a-z][a-z0-9 -]*?)(?:[.!]|$)",
            re.IGNORECASE,
        ),
        "grocery.preferred_snack",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\bI confirm that my preferred (?P<value>[a-z][a-z0-9 -]*?) "
            r"as (?:my )?snack\b",
            re.IGNORECASE,
        ),
        "grocery.preferred_snack",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\b(?:I )?(?:usually|always) prefer bananas? (?:that are )?"
            r"(?P<value>[a-z_ ]+?)(?:\.|$)",
            re.IGNORECASE,
        ),
        "grocery.banana_ripeness",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\b(?:I )?(?:usually|always) prefer tomatoes? (?:that are )?(?:still )?"
            r"(?P<value>firm|soft)(?:\.|$)",
            re.IGNORECASE,
        ),
        "grocery.tomato_firmness",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\b(?:I )?(?:usually|always) (?:prefer )?cereal "
            r"(?P<value>only when discounted)(?:\.|$)",
            re.IGNORECASE,
        ),
        "grocery.cereal_purchase_rule",
        "grocery",
        PreferenceScope.LONG_TERM,
    ),
    _Rule(
        re.compile(
            r"\b(?:I )?(?:usually |always )?prefer "
            r"(?P<value>evening|6PM-8PM) delivery\b",
            re.IGNORECASE,
        ),
        "delivery.preferred_window",
        "delivery",
        PreferenceScope.LONG_TERM,
    ),
)


def extract_grocery_candidate(
    message: str, *, user_id: str, session_id: str
) -> PreferenceCandidate | None:
    """Transparent POC extractor; policy remains authoritative after extraction.

    ADK models occasionally pass a concise preference clause instead of the entire user
    utterance. A narrowly scoped substitution clause is therefore treated as a session
    preference; durable writes still require an explicit durability phrase.
    """
    for rule in _RULES:
        match = rule.pattern.search(message)
        if not match:
            continue
        value = rule.fixed_value
        if value is None:
            value = match.group("value").strip().replace(" ", "_")
            if rule.key == "grocery.budget":
                value = float(value)
            if rule.key == "delivery.preferred_window" and str(value).lower() == "evening":
                value = "6PM-8PM"
        return PreferenceCandidate(
            key=rule.key,
            value=value,
            proposed_domain=rule.domain,
            requested_scope=rule.scope,
            confidence=0.99,
            source="GROCERY_AGENT_EXTRACTOR",
            source_message=message,
            user_id=user_id,
            session_id=session_id,
            explicit=True,
            evidence="explicit temporal or durability phrase",
        )
    return None
