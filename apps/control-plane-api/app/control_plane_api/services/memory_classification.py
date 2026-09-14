"""Deterministic content classification for memory writes.

Scans a candidate memory value for categories that raise its sensitivity tier. This is a
pattern-based backstop (defense in depth), not a semantic classifier: it reliably catches restricted
categories (PII, weapons, discriminatory targeting) and flags protected-class content as sensitive,
but it does not detect subtle inferences (e.g. deriving religion from "avoid pork"). Category
patterns are intended to be config-extendable.
"""

from __future__ import annotations

import re

from control_plane_api.domain.sensitivity import SensitivityTier

# (category label, tier the match forces, pattern). Ordered most-severe first.
_CATEGORY_PATTERNS: tuple[tuple[str, SensitivityTier, re.Pattern[str]], ...] = (
    ("pii_ssn", SensitivityTier.RESTRICTED, re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("pii_card", SensitivityTier.RESTRICTED, re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("pii_phone", SensitivityTier.RESTRICTED, re.compile(r"(?:\+?\d[\s.-]?){10,}")),
    ("pii_email", SensitivityTier.RESTRICTED, re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("credential", SensitivityTier.RESTRICTED, re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\b")),
    ("weapons", SensitivityTier.RESTRICTED, re.compile(r"(?i)\b(guns?|firearms?|rifles?|pistols?|ammunition|ammo)\b")),
    (
        "discrimination",
        SensitivityTier.RESTRICTED,
        re.compile(
            r"(?i)\b(?:don'?t|do not|never)\s+let\s+.{0,40}?\b(?:person|people)\b"
            r"|\b(?:race|racial|ethnic\w*|religio\w*)\b.{0,30}?\b(?:pick|serve|choose|assign|refuse)\b"
        ),
    ),
    (
        "protected_class",
        SensitivityTier.SENSITIVE,
        re.compile(
            r"(?i)\b(muslim|jewish|christian|catholic|hindu|buddhist|islam|judaism|christianity"
            r"|pregnan\w*|diabet\w*|cancer|hiv|disab\w*|medication)\b"
        ),
    ),
)


def classify_content(value: object) -> tuple[SensitivityTier, str | None]:
    """Return the highest sensitivity tier implied by the value's content and the matched category."""
    if not isinstance(value, str):
        return SensitivityTier.NON_SENSITIVE, None
    for category, tier, pattern in _CATEGORY_PATTERNS:
        if pattern.search(value):
            return tier, category
    return SensitivityTier.NON_SENSITIVE, None
