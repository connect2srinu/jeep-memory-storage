from __future__ import annotations

import pytest
from control_plane_api.domain.sensitivity import SensitivityTier
from control_plane_api.services.memory_classification import classify_content, redact_for_log


@pytest.mark.parametrize(
    "value,tier,category",
    [
        ("I like oat milk", SensitivityTier.NON_SENSITIVE, None),
        ("shops early Sunday mornings", SensitivityTier.NON_SENSITIVE, None),
        ("wishes he could bring his guns into the store", SensitivityTier.RESTRICTED, "weapons"),
        ("call me at 555-123-4567", SensitivityTier.RESTRICTED, "pii_phone"),
        ("my email is a@b.com", SensitivityTier.RESTRICTED, "pii_email"),
        ("don't let a black person pick my groceries", SensitivityTier.RESTRICTED, "discrimination"),
        ("user is Muslim", SensitivityTier.SENSITIVE, "protected_class"),
        ("has Type 2 diabetes", SensitivityTier.SENSITIVE, "protected_class"),
    ],
)
def test_classify_content(value, tier, category) -> None:
    result_tier, result_category = classify_content(value)
    assert result_tier is tier
    assert result_category == category


def test_non_string_is_non_sensitive() -> None:
    assert classify_content(42) == (SensitivityTier.NON_SENSITIVE, None)


@pytest.mark.parametrize(
    "value,tier,health,logged",
    [
        ("oat milk", SensitivityTier.NON_SENSITIVE, False, "oat milk"),
        ("my SSN is 123-45-6789", SensitivityTier.RESTRICTED, False, "my SSN is ***"),
        ("user is Muslim", SensitivityTier.SENSITIVE, False, "user is ***"),
        ("walks daily", SensitivityTier.SENSITIVE, False, "***"),  # sensitive only by declaration
        ("peanuts", SensitivityTier.NON_SENSITIVE, True, "***"),  # health data
        (True, SensitivityTier.NON_SENSITIVE, False, True),
    ],
)
def test_redact_for_log(value, tier, health, logged) -> None:
    assert redact_for_log(value, tier, health=health) == logged
