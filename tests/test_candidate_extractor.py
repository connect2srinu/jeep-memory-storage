from __future__ import annotations

import unittest

from app.preferences.candidate_extractor import extract_candidate
from app.preferences.models import PreferenceScope


class CandidateExtractorTests(unittest.TestCase):
    def test_today_is_session_only(self) -> None:
        candidate = extract_candidate("For today's order, substitutions are okay.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.key, "allow_substitutions")
        self.assertIs(candidate.requested_scope, PreferenceScope.SESSION)

    def test_always_is_long_term_candidate(self) -> None:
        candidate = extract_candidate("I always prefer oat milk.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.key, "preferred_milk")
        self.assertIs(candidate.requested_scope, PreferenceScope.USER)

    def test_incidental_choice_is_not_promoted(self) -> None:
        self.assertIsNone(extract_candidate("Add oat milk to my cart."))

    def test_ignore_personal_diet_is_session_override(self) -> None:
        candidate = extract_candidate(
            "Today I am shopping for my parents, so don't apply my vegetarian preference."
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual((candidate.key, candidate.value), ("diet", "none"))
        self.assertIs(candidate.requested_scope, PreferenceScope.SESSION)

    def test_trip_budget_is_numeric_session_override(self) -> None:
        candidate = extract_candidate("For this trip, keep the total under $100.")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual((candidate.key, candidate.value), ("budget", 100.0))


if __name__ == "__main__":
    unittest.main()
