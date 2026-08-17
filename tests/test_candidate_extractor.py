from __future__ import annotations

import unittest

from app.agents.grocery_extraction import extract_grocery_candidate
from app.shared_memory.models import PreferenceScope


def extract(message: str):
    return extract_grocery_candidate(message, user_id="U123", session_id="S456")


class CandidateExtractorTests(unittest.TestCase):
    def test_concise_substitution_clause_is_a_session_candidate(self) -> None:
        candidate = extract("substitutions are okay")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.key, "grocery.allow_substitutions")
        self.assertIs(candidate.value, True)
        self.assertIs(candidate.requested_scope, PreferenceScope.SESSION)

    def test_today_is_session_only(self) -> None:
        candidate = extract("For today's order, substitutions are okay.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.key, "grocery.allow_substitutions")
        self.assertIs(candidate.requested_scope, PreferenceScope.SESSION)

    def test_always_is_long_term_candidate(self) -> None:
        candidate = extract("I always prefer oat milk.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.key, "grocery.preferred_milk")
        self.assertIs(candidate.requested_scope, PreferenceScope.LONG_TERM)

    def test_incidental_choice_is_not_promoted(self) -> None:
        self.assertIsNone(extract("Add oat milk to my cart."))

    def test_ignore_personal_diet_becomes_grocery_session_override(self) -> None:
        candidate = extract(
            "Today I am shopping for my parents, so don't apply my vegetarian preference."
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual((candidate.key, candidate.value), ("grocery.diet_override", "none"))
        self.assertIs(candidate.requested_scope, PreferenceScope.SESSION)

    def test_trip_budget_is_numeric_session_override(self) -> None:
        candidate = extract("For this trip, keep the total under $100.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual((candidate.key, candidate.value), ("grocery.budget", 100.0))

    def test_open_ended_banana_preference_is_dynamic_candidate(self) -> None:
        candidate = extract("I usually prefer bananas that are slightly green.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.key, "grocery.banana_ripeness")


if __name__ == "__main__":
    unittest.main()
