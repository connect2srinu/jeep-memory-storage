"""Household-local identity resolution: match a person the customer mentions to a household member.

Matching is scoped to one household (typically 1-8 members), so it never searches across customers.
Pure functions only — the runtime service loads the household and applies the decision.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

# Starting thresholds (design doc "Confidence tiers"); tune on a labeled set of name variants.
AUTO_MATCH_THRESHOLD = 0.92
ASK_THRESHOLD = 0.80
# A phonetic (Soundex) agreement nudges a close string score, but never rescues a distant one.
_PHONETIC_BONUS = 0.03

MemberKind = Literal["ROOT", "DEPENDENT", "PROXY_ADULT"]

# relationship word -> (group, gender). Gender None means the word doesn't imply one.
_RELATIONSHIPS: dict[str, tuple[str, str | None]] = {
    "son": ("child", "m"),
    "daughter": ("child", "f"),
    "child": ("child", None),
    "kid": ("child", None),
    "boy": ("child", "m"),
    "girl": ("child", "f"),
    "baby": ("child", None),
    "toddler": ("child", None),
    "stepson": ("child", "m"),
    "stepdaughter": ("child", "f"),
    "grandson": ("child", "m"),
    "granddaughter": ("child", "f"),
    "grandchild": ("child", None),
    "wife": ("partner", "f"),
    "husband": ("partner", "m"),
    "spouse": ("partner", None),
    "partner": ("partner", None),
    "girlfriend": ("partner", "f"),
    "boyfriend": ("partner", "m"),
    "fiance": ("partner", None),
    "fiancee": ("partner", None),
    "mother": ("parent", "f"),
    "mom": ("parent", "f"),
    "mum": ("parent", "f"),
    "father": ("parent", "m"),
    "dad": ("parent", "m"),
    "parent": ("parent", None),
    "grandmother": ("grandparent", "f"),
    "grandma": ("grandparent", "f"),
    "grandfather": ("grandparent", "m"),
    "grandpa": ("grandparent", "m"),
    "grandparent": ("grandparent", None),
    "brother": ("sibling", "m"),
    "sister": ("sibling", "f"),
    "sibling": ("sibling", None),
    "roommate": ("other", None),
    "friend": ("other", None),
    "accountholder": ("self", None),
    "self": ("self", None),
}
_SELF_REFERENCES = frozenset({"me", "myself", "i", "self"})


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation and possessives, collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_only.lower()
    lowered = re.sub(r"['’]s\b", "", lowered)
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return " ".join(cleaned.split())


def is_self_reference(name: str | None) -> bool:
    return bool(name) and normalize_name(name) in _SELF_REFERENCES


def _relationship_key(relationship: str | None) -> str:
    if not relationship:
        return ""
    value = relationship.lower().strip()
    value = re.sub(r"^(my|our)\s+", "", value)
    return re.sub(r"[\s_\-]+", "", value)


def relationship_info(relationship: str | None) -> tuple[str, str | None]:
    """(group, gender) for a relationship word; ("unknown", None) when not recognized."""
    return _RELATIONSHIPS.get(_relationship_key(relationship), ("unknown", None))


def member_kind_for(relationship: str | None, *, has_login: bool) -> tuple[MemberKind, bool]:
    """The member kind and default minor flag implied by a relationship.

    A login makes the person a household root. A child relationship is a dependent and a minor by
    default (the user can correct it, e.g. an adult son). Anyone else is a proxy adult.
    """
    if has_login:
        return "ROOT", False
    group, _ = relationship_info(relationship)
    if group == "child":
        return "DEPENDENT", True
    return "PROXY_ADULT", False


def relationships_compatible(first: str | None, second: str | None) -> bool:
    """False when the relationships clearly describe different people (son vs daughter, child vs
    spouse). Unknown relationships are compatible with anything."""
    group_a, gender_a = relationship_info(first)
    group_b, gender_b = relationship_info(second)
    if "unknown" in (group_a, group_b):
        return True
    if group_a != group_b:
        return False
    return not (gender_a and gender_b and gender_a != gender_b)


def jaro_winkler(first: str, second: str, prefix_scale: float = 0.1) -> float:
    if first == second:
        return 1.0
    len_a, len_b = len(first), len(second)
    if not len_a or not len_b:
        return 0.0
    window = max(max(len_a, len_b) // 2 - 1, 0)
    matched_a = [False] * len_a
    matched_b = [False] * len_b
    matches = 0
    for i, char in enumerate(first):
        for j in range(max(0, i - window), min(i + window + 1, len_b)):
            if not matched_b[j] and second[j] == char:
                matched_a[i] = matched_b[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(len_a):
        if matched_a[i]:
            while not matched_b[k]:
                k += 1
            if first[i] != second[k]:
                transpositions += 1
            k += 1
    jaro = (matches / len_a + matches / len_b + (matches - transpositions / 2) / matches) / 3
    prefix = 0
    for char_a, char_b in zip(first, second, strict=False):
        if char_a != char_b or prefix == 4:
            break
        prefix += 1
    return jaro + prefix * prefix_scale * (1 - jaro)


def soundex(name: str) -> str:
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    letters = [ch for ch in name.lower() if ch.isalpha()]
    if not letters:
        return ""
    result = letters[0].upper()
    previous = codes.get(letters[0], "")
    for char in letters[1:]:
        code = codes.get(char, "")
        if code and code != previous:
            result += code
        if char not in "hw":
            previous = code
    return (result + "000")[:4]


def name_score(reference: str, candidate: str) -> float:
    """Similarity of two normalized names in [0, 1]."""
    score = jaro_winkler(reference, candidate)
    if score >= ASK_THRESHOLD and soundex(reference) == soundex(candidate):
        score = min(score + _PHONETIC_BONUS, 0.99)
    return score


@dataclass(frozen=True, slots=True)
class MemberCandidate:
    member_id: str
    display_name: str | None
    relationship: str
    # Normalized display name plus normalized aliases.
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Resolution:
    status: Literal["matched", "ambiguous", "new"]
    candidate: MemberCandidate | None = None
    score: float = 0.0
    # True when a non-exact variant matched — the caller should record it as an alias.
    variant: bool = False
    candidates: tuple[MemberCandidate, ...] = ()


def resolve_reference(
    name: str,
    relationship: str | None,
    candidates: tuple[MemberCandidate, ...],
    *,
    strict: bool,
) -> Resolution:
    """Match a mentioned person to a household member.

    ``strict`` (health data) only accepts an exact name or known alias; anything close asks. A
    mention matches at most one member, and incompatible relationships are never matched.
    """
    reference = normalize_name(name)
    if not reference:
        raise ValueError("a member name is required")
    scored: list[tuple[float, bool, MemberCandidate]] = []
    for candidate in candidates:
        if not relationships_compatible(relationship, candidate.relationship):
            continue
        if not candidate.names:
            continue
        best = max(name_score(reference, known) for known in candidate.names)
        scored.append((best, reference in candidate.names, candidate))

    exact = [candidate for _, is_exact, candidate in scored if is_exact]
    if len(exact) == 1:
        return Resolution("matched", exact[0], 1.0)
    if len(exact) > 1:
        return Resolution("ambiguous", candidates=tuple(exact))

    near = [(score, candidate) for score, _, candidate in scored if score >= ASK_THRESHOLD]
    high = [(score, candidate) for score, candidate in near if score >= AUTO_MATCH_THRESHOLD]
    if not strict and len(high) == 1 and len(near) == 1:
        score, candidate = high[0]
        return Resolution("matched", candidate, score, variant=True)
    if near:
        ordered = sorted(near, key=lambda item: item[0], reverse=True)
        return Resolution("ambiguous", candidates=tuple(candidate for _, candidate in ordered))
    return Resolution("new")


# --- Prompts: worded by the platform so the consent ledger records platform-controlled text. ---


def attribute_label(attribute_id: str) -> str:
    return attribute_id.rsplit(".", 1)[-1].replace("_", " ")


def describe_member(display_name: str | None, relationship: str | None) -> str:
    name = display_name or "this person"
    group, _ = relationship_info(relationship)
    if relationship and group not in {"unknown", "self"}:
        return f"{name} (your {relationship})"
    return name


def new_member_prompt(
    display_name: str,
    relationship: str | None,
    fact: tuple[str, Any] | None = None,
) -> str:
    text = f"Should I add {describe_member(display_name, relationship)} to your household"
    if fact is not None:
        attribute, value = fact
        text += f' and save their {attribute_label(attribute)} as "{value}"'
    return text + "?"


def health_prompt(attribute_id: str, value: Any, subject: str) -> str:
    return f'Please confirm: save {attribute_label(attribute_id)} as "{value}" for {subject}?'


def ambiguous_prompt(name: str, candidates: tuple[MemberCandidate, ...]) -> str:
    options = " or ".join(
        describe_member(item.display_name, item.relationship) for item in candidates
    )
    return f'Which "{name}" do you mean: {options}? Or is this someone new?'


def merge_prompt(keep: str, merge: str) -> str:
    return (
        f"Merge {merge} into {keep}? {merge}'s saved preferences move to {keep}, "
        f"and {merge} is removed from your household."
    )


def value_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
