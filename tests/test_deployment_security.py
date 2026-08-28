from __future__ import annotations

from scripts.validate_deployment_security import AUTH_DISABLED_PATTERN, main


def test_deployment_security_policy() -> None:
    main()


def test_auth_guardrail_matches_only_primary_auth_flag() -> None:
    assert AUTH_DISABLED_PATTERN.search("AUTH_ENABLED=false")
    assert AUTH_DISABLED_PATTERN.search("AUTH_ENABLED = 0")
    assert not AUTH_DISABLED_PATTERN.search("ENTRA_AUTH_ENABLED=false")
    assert not AUTH_DISABLED_PATTERN.search("VITE_ENTRA_AUTH_ENABLED=false")
