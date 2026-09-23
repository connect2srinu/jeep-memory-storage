"""Household-local identity resolution: normalization, similarity, relationships, decisions."""

from __future__ import annotations

import pytest
from control_plane_api.domain.household_identity import (
    MemberCandidate,
    jaro_winkler,
    member_kind_for,
    name_score,
    new_member_prompt,
    normalize_name,
    relationships_compatible,
    resolve_reference,
    soundex,
)


def candidate(member_id: str, name: str, relationship: str, *aliases: str) -> MemberCandidate:
    return MemberCandidate(
        member_id=member_id,
        display_name=name,
        relationship=relationship,
        names=(normalize_name(name), *aliases),
    )


def test_normalize_strips_accents_case_and_possessives() -> None:
    assert normalize_name("  Aníka's ") == "anika"
    assert normalize_name("Mary-Jane") == "mary jane"


def test_similarity_signals() -> None:
    assert jaro_winkler("anika", "anika") == 1.0
    assert jaro_winkler("anika", "anikaa") > 0.92
    assert jaro_winkler("ryan", "brian") < 0.80
    assert soundex("Anika") == soundex("Anikaa") == "A520"
    # A phonetic match never rescues a distant name.
    assert name_score("ryan", "brian") < 0.80


def test_relationship_kind_and_compatibility() -> None:
    assert member_kind_for("son", has_login=False) == ("DEPENDENT", True)
    assert member_kind_for("my wife", has_login=False) == ("PROXY_ADULT", False)
    assert member_kind_for("child", has_login=True) == ("ROOT", False)
    assert relationships_compatible("son", "child")
    assert not relationships_compatible("son", "daughter")
    assert not relationships_compatible("child", "wife")
    assert relationships_compatible(None, "daughter")


def test_resolution_tiers() -> None:
    members = (
        candidate("m1", "Anika", "daughter"),
        candidate("m2", "Ryan", "son"),
    )
    # Exact name matches; a close variant auto-matches (and is flagged to learn as an alias).
    assert resolve_reference("Ryan", "son", members, strict=False).candidate.member_id == "m2"
    variant = resolve_reference("Anikaa", None, members, strict=False)
    assert variant.status == "matched" and variant.variant
    # Health data (strict) only accepts an exact name or alias — a variant asks.
    assert resolve_reference("Anikaa", None, members, strict=True).status == "ambiguous"
    # A different person, and an incompatible relationship, are new.
    assert resolve_reference("Brian", None, members, strict=False).status == "new"
    assert resolve_reference("Ryan", "brother", members, strict=False).status == "new"


def test_two_close_candidates_ask_rather_than_guess() -> None:
    members = (candidate("m1", "Sam", "son"), candidate("m2", "Sam", "daughter"))
    result = resolve_reference("Sam", None, members, strict=False)
    assert result.status == "ambiguous" and len(result.candidates) == 2
    assert resolve_reference("Sam", "daughter", members, strict=False).candidate.member_id == "m2"


def test_aliases_match_exactly() -> None:
    members = (candidate("m1", "Anika", "daughter", "kiki"),)
    assert resolve_reference("Kiki", None, members, strict=True).candidate.member_id == "m1"


def test_prompts_are_platform_worded() -> None:
    text = new_member_prompt("Ryan", "son", ("familygrocery.allergies", "peanuts"))
    assert text == (
        'Should I add Ryan (your son) to your household and save their allergies as "peanuts"?'
    )
    with pytest.raises(ValueError):
        resolve_reference("  ", None, (), strict=False)
