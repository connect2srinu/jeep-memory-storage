from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import httpx

from app.shared_memory.adapters import (
    InMemoryLongTermMemoryAdapter,
    InMemorySessionAdapter,
    MockProfileAdapter,
    NullMemoryProfileAdapter,
)
from app.shared_memory.api import create_api_app
from app.shared_memory.auth import AuthorizationService
from app.shared_memory.catalog import PreferenceCatalog
from app.shared_memory.models import (
    CandidateDisposition,
    Preference,
    PreferenceCandidate,
    PreferenceScope,
    PreferenceSource,
)
from app.shared_memory.policies import PreferencePolicyRegistry
from app.shared_memory.resolver import PreferenceResolver
from app.shared_memory.services import (
    InMemoryCandidateRepository,
    InMemorySnapshotService,
    LongTermMemoryService,
    PreferenceContextService,
    ProfilePreferenceService,
    SessionContextService,
    SharedMemoryPlatformService,
)


def preference(
    key: str,
    value: object,
    source: PreferenceSource,
    domain: str,
    *,
    confidence: float | None = 1.0,
    updated_at: datetime | None = None,
    expires_at: datetime | None = None,
    provenance: dict[str, object] | None = None,
) -> Preference:
    return Preference(
        key=key,
        value=value,
        source=source,
        owner_domain=domain,
        scope=(
            PreferenceScope.SESSION
            if source is PreferenceSource.SESSION_OVERRIDE
            else PreferenceScope.LONG_TERM
        ),
        confidence=confidence,
        updated_at=updated_at or datetime.now(UTC),
        expires_at=expires_at,
        confirmed=source is not PreferenceSource.INFERRED_MEMORY,
        canonical="." in key and key != "grocery.banana_ripeness",
        provenance=provenance or {},
    )


class StaticProfileAdapter:
    def __init__(self, values: list[Preference]) -> None:
        self.values = values

    async def get_preferences(
        self, user_id: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        del user_id
        return [item for item in self.values if item.owner_domain in domains]


class FailingProfileAdapter:
    async def get_preferences(
        self, user_id: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        del user_id, domains
        raise RuntimeError("profile unavailable")


class FailingDynamicMemoryAdapter:
    async def get_dynamic_preferences(
        self, user_id: str, app_name: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        del user_id, app_name, domains
        raise RuntimeError("memory unavailable")

    async def store_dynamic_preference(
        self, user_id: str, app_name: str, value: Preference
    ) -> str:
        del user_id, app_name, value
        raise RuntimeError("memory unavailable")


class FailingSessionAdapter:
    async def get_session_preferences(
        self, user_id: str, session_id: str, domains: tuple[str, ...]
    ) -> list[Preference]:
        del user_id, session_id, domains
        raise RuntimeError("session unavailable")

    async def save_session_preference(
        self, user_id: str, session_id: str, value: Preference
    ) -> None:
        del user_id, session_id, value
        raise RuntimeError("session unavailable")


def build_platform(
    *,
    session_backend: object | None = None,
    profile_adapter: object | None = None,
    dynamic_backend: object | None = None,
) -> tuple[SharedMemoryPlatformService, object, object, InMemoryCandidateRepository]:
    catalog = PreferenceCatalog.default()
    policies = PreferencePolicyRegistry.default(0.7)
    authorization = AuthorizationService(policies)
    resolver = PreferenceResolver(catalog, policies)
    session_backend = session_backend or InMemorySessionAdapter()
    dynamic_backend = dynamic_backend or InMemoryLongTermMemoryAdapter()
    profile_adapter = profile_adapter or StaticProfileAdapter([])
    session_service = SessionContextService(session_backend)  # type: ignore[arg-type]
    long_term_service = LongTermMemoryService(
        dynamic_backend,  # type: ignore[arg-type]
        NullMemoryProfileAdapter(),
    )
    snapshot = InMemorySnapshotService()
    candidates = InMemoryCandidateRepository()
    context_service = PreferenceContextService(
        session_service=session_service,
        profile_service=ProfilePreferenceService((profile_adapter,)),  # type: ignore[arg-type]
        long_term_service=long_term_service,
        catalog=catalog,
        policies=policies,
        authorization=authorization,
        resolver=resolver,
        snapshot_service=snapshot,
        app_name="shared-memory-test",
    )
    platform = SharedMemoryPlatformService(
        context_service=context_service,
        session_service=session_service,
        long_term_service=long_term_service,
        catalog=catalog,
        authorization=authorization,
        snapshot_service=snapshot,
        candidate_repository=candidates,
        app_name="shared-memory-test",
    )
    return platform, session_backend, dynamic_backend, candidates


class ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = PreferenceCatalog.default()
        self.policies = PreferencePolicyRegistry.default(0.7)
        self.resolver = PreferenceResolver(self.catalog, self.policies)

    def resolve(self, values: list[Preference], domain: str = "grocery"):
        readable = self.policies.domain_policy(domain).read
        return self.resolver.resolve(
            user_id="U123",
            session_id="S456",
            consumer_domain=domain,
            agent_id=f"{domain}-agent",
            preferences=values,
            readable_domains=readable,
        )

    def test_session_overrides_everything(self) -> None:
        context = self.resolve(
            [
                preference(
                    "grocery.allow_substitutions", False, PreferenceSource.EXPLICIT_PROFILE, "grocery"
                ),
                preference(
                    "grocery.allow_substitutions", True, PreferenceSource.SESSION_OVERRIDE, "grocery"
                ),
            ]
        )
        self.assertTrue(context.preferences["allow_substitutions"].preference.value)

    def test_explicit_profile_overrides_long_term_memory(self) -> None:
        context = self.resolve(
            [
                preference("grocery.preferred_milk", "oat milk", PreferenceSource.DYNAMIC_MEMORY, "grocery"),
                preference("grocery.preferred_milk", "whole milk", PreferenceSource.EXPLICIT_PROFILE, "grocery"),
            ]
        )
        self.assertEqual(context.preferences["preferred_milk"].preference.value, "whole milk")

    def test_owner_domain_wins_where_policy_specifies(self) -> None:
        context = self.resolve(
            [
                preference("store.preferred_product_type", "conventional", PreferenceSource.EXPLICIT_PROFILE, "store"),
                preference("grocery.preferred_product_type", "organic", PreferenceSource.EXPLICIT_PROFILE, "grocery"),
            ]
        )
        self.assertEqual(context.preferences["preferred_product_type"].preference.owner_domain, "grocery")

    def test_grocery_beats_store_for_product_preference(self) -> None:
        context = self.resolve(
            [
                preference("store.preferred_product_type", "store", PreferenceSource.DOMAIN_MEMORY, "store"),
                preference("grocery.preferred_product_type", "grocery", PreferenceSource.DOMAIN_MEMORY, "grocery"),
            ]
        )
        self.assertEqual(context.preferences["preferred_product_type"].preference.value, "grocery")

    def test_delivery_wins_for_delivery_attribute(self) -> None:
        context = self.resolve(
            [
                preference("grocery.preferred_window", "noon", PreferenceSource.DOMAIN_MEMORY, "grocery"),
                preference("delivery.preferred_window", "6PM-8PM", PreferenceSource.DOMAIN_MEMORY, "delivery"),
            ]
        )
        self.assertEqual(context.preferences["preferred_window"].preference.owner_domain, "delivery")

    def test_dynamic_preference_participates(self) -> None:
        context = self.resolve(
            [preference("grocery.banana_ripeness", "slightly_green", PreferenceSource.DYNAMIC_MEMORY, "grocery")]
        )
        self.assertEqual(context.preferences["banana_ripeness"].preference.value, "slightly_green")

    def test_expired_preference_is_ignored(self) -> None:
        context = self.resolve(
            [
                preference(
                    "grocery.banana_ripeness",
                    "brown",
                    PreferenceSource.DYNAMIC_MEMORY,
                    "grocery",
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            ]
        )
        self.assertNotIn("banana_ripeness", context.preferences)

    def test_low_confidence_inferred_preference_is_filtered(self) -> None:
        context = self.resolve(
            [
                preference(
                    "grocery.tomato_firmness",
                    "firm",
                    PreferenceSource.INFERRED_MEMORY,
                    "grocery",
                    confidence=0.2,
                )
            ]
        )
        self.assertNotIn("tomato_firmness", context.preferences)

    def test_provenance_is_preserved(self) -> None:
        context = self.resolve(
            [
                preference(
                    "grocery.banana_ripeness",
                    "green",
                    PreferenceSource.DYNAMIC_MEMORY,
                    "grocery",
                    provenance={"memory_name": "memory-1"},
                )
            ]
        )
        selected = context.preferences["banana_ripeness"].preference
        self.assertEqual(selected.provenance["memory_name"], "memory-1")


class AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = PreferenceCatalog.default()
        self.authorization = AuthorizationService(PreferencePolicyRegistry.default())

    def test_grocery_can_write_grocery(self) -> None:
        entry = self.catalog.lookup("grocery.preferred_brand")
        self.assertTrue(self.authorization.can_write("grocery", "grocery", entry).allowed)

    def test_grocery_can_read_customer(self) -> None:
        entry = self.catalog.lookup("customer.preferred_store")
        self.assertTrue(self.authorization.can_read("grocery", "customer", entry).allowed)

    def test_grocery_cannot_write_delivery(self) -> None:
        entry = self.catalog.lookup("delivery.preferred_window")
        self.assertFalse(self.authorization.can_write("grocery", "delivery", entry).allowed)

    def test_grocery_cannot_read_pharmacy(self) -> None:
        self.assertFalse(self.authorization.can_read("grocery", "pharmacy").allowed)


class PlatformBehaviorTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def candidate(
        key: str,
        domain: str,
        scope: PreferenceScope,
        value: object = "value",
    ) -> PreferenceCandidate:
        return PreferenceCandidate(
            key=key,
            value=value,
            proposed_domain=domain,
            requested_scope=scope,
            confidence=0.95,
            source="TEST",
            source_message="test",
            user_id="U123",
            session_id="S456",
        )

    async def test_unknown_preference_becomes_dynamic_memory(self) -> None:
        platform, _, memory, _ = build_platform()
        result = await platform.submit_preference(
            candidate=self.candidate(
                "banana_ripeness", "grocery", PreferenceScope.LONG_TERM, "slightly_green"
            ),
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertEqual(result.disposition, CandidateDisposition.STORED_IN_DYNAMIC_MEMORY)
        self.assertFalse(result.canonical_key == "banana_ripeness")
        self.assertEqual(len(memory._items), 1)  # type: ignore[attr-defined]

    async def test_canonical_preference_uses_catalog_definition(self) -> None:
        platform, session, _, _ = build_platform()
        result = await platform.submit_preference(
            candidate=self.candidate(
                "allow_substitutions", "grocery", PreferenceScope.SESSION, True
            ),
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertEqual(result.canonical_key, "grocery.allow_substitutions")
        self.assertEqual(result.disposition, CandidateDisposition.STORED_IN_SESSION)
        self.assertTrue(session.state("U123", "S456"))  # type: ignore[attr-defined]

    async def test_grocery_snack_routes_to_grocery_long_term_memory(self) -> None:
        platform, _, memory, candidates = build_platform()
        result = await platform.submit_preference(
            candidate=self.candidate(
                "preferred_snack", "grocery", PreferenceScope.LONG_TERM, "mango_chips"
            ),
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertEqual(result.canonical_key, "grocery.preferred_snack")
        self.assertEqual(result.owner_domain, "grocery")
        self.assertEqual(result.disposition, CandidateDisposition.STORED_IN_DYNAMIC_MEMORY)
        self.assertEqual(len(memory._items), 1)  # type: ignore[attr-defined]
        self.assertEqual(len(candidates.items), 0)

    async def test_cross_domain_preference_becomes_candidate(self) -> None:
        platform, _, memory, candidates = build_platform()
        result = await platform.submit_preference(
            candidate=self.candidate(
                "preferred_window", "delivery", PreferenceScope.LONG_TERM, "6PM-8PM"
            ),
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertEqual(result.disposition, CandidateDisposition.CROSS_DOMAIN_CANDIDATE)
        self.assertEqual(len(candidates.items), 1)
        self.assertEqual(len(memory._items), 0)  # type: ignore[attr-defined]

    async def test_memory_bank_failure_preserves_profile(self) -> None:
        profile_value = preference(
            "customer.preferred_store", "Store-084", PreferenceSource.EXPLICIT_PROFILE, "customer"
        )
        platform, _, _, _ = build_platform(
            profile_adapter=StaticProfileAdapter([profile_value]),
            dynamic_backend=FailingDynamicMemoryAdapter(),
        )
        context = await platform.get_effective_context(
            user_id="U123", session_id="S456", consumer_domain="grocery", agent_id="grocery-agent"
        )
        self.assertEqual(context.preferences["preferred_store"].preference.value, "Store-084")
        self.assertIn("dynamic_memory unavailable", context.warnings)

    async def test_profile_failure_preserves_dynamic_memory(self) -> None:
        memory = InMemoryLongTermMemoryAdapter(
            [("U123", "shared-memory-test", preference("grocery.banana_ripeness", "green", PreferenceSource.DYNAMIC_MEMORY, "grocery"))]
        )
        platform, _, _, _ = build_platform(
            profile_adapter=FailingProfileAdapter(), dynamic_backend=memory
        )
        context = await platform.get_effective_context(
            user_id="U123", session_id="S456", consumer_domain="grocery", agent_id="grocery-agent"
        )
        self.assertEqual(context.preferences["banana_ripeness"].preference.value, "green")
        self.assertIn("explicit_profile unavailable", context.warnings)

    async def test_session_failure_preserves_profile(self) -> None:
        profile_value = preference(
            "customer.preferred_store", "Store-084", PreferenceSource.EXPLICIT_PROFILE, "customer"
        )
        platform, _, _, _ = build_platform(
            session_backend=FailingSessionAdapter(),
            profile_adapter=StaticProfileAdapter([profile_value]),
        )
        context = await platform.get_effective_context(
            user_id="U123", session_id="S456", consumer_domain="grocery", agent_id="grocery-agent"
        )
        self.assertEqual(context.preferences["preferred_store"].preference.value, "Store-084")
        self.assertIn("session unavailable", context.warnings)

    async def test_grocery_receives_one_context_without_backend_knowledge(self) -> None:
        catalog = PreferenceCatalog.default()
        platform, _, _, _ = build_platform(profile_adapter=MockProfileAdapter(catalog))
        context = await platform.get_effective_context(
            user_id="U123", session_id="S456", consumer_domain="grocery", agent_id="grocery-agent"
        )
        self.assertEqual(context.consumer_domain, "grocery")
        self.assertIn("preferred_store", context.preferences)
        self.assertNotIn("source_queries", context.to_dict())

    async def test_api_exposes_required_routes(self) -> None:
        platform, _, _, _ = build_platform()
        api = create_api_app(platform)
        paths = {route.path for route in api.routes}
        self.assertIn("/v1/memory/context/resolve", paths)
        self.assertIn("/v1/memory/preferences", paths)
        self.assertIn("/v1/memory/users/{user_id}/effective-context", paths)

    async def test_api_submits_and_resolves_session_preference(self) -> None:
        platform, _, _, _ = build_platform()
        transport = httpx.ASGITransport(app=create_api_app(platform))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            submitted = await client.post(
                "/v1/memory/preferences",
                json={
                    "userId": "U123",
                    "sessionId": "S456",
                    "consumerDomain": "grocery",
                    "agentId": "grocery-agent",
                    "key": "allow_substitutions",
                    "value": True,
                    "proposedDomain": "grocery",
                    "requestedScope": "SESSION",
                },
            )
            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["status"], "STORED_IN_SESSION")
            resolved = await client.post(
                "/v1/memory/context/resolve",
                json={
                    "userId": "U123",
                    "sessionId": "S456",
                    "consumerDomain": "grocery",
                    "agentId": "grocery-agent",
                    "context": {},
                },
            )
            self.assertEqual(resolved.status_code, 200)
            selected = resolved.json()["preferences"]["allow_substitutions"]
            self.assertTrue(selected["value"])
            self.assertEqual(selected["source"], "SESSION_OVERRIDE")

    async def test_readonly_consumer_gets_redacted_provenance_and_separate_cache(self) -> None:
        value = preference(
            "grocery.preferred_brand",
            "Simple Truth",
            PreferenceSource.EXPLICIT_PROFILE,
            "grocery",
            provenance={"service": "authoritative-profile", "record_id": "secret-reference"},
        )
        platform, _, _, _ = build_platform(profile_adapter=StaticProfileAdapter([value]))

        readonly = await platform.get_effective_context(
            user_id="U123",
            session_id="S456",
            consumer_domain="grocery",
            agent_id="grocery-readonly-agent",
        )
        self.assertEqual(readonly.preferences["preferred_brand"].preference.provenance, {})

        full = await platform.get_effective_context(
            user_id="U123",
            session_id="S456",
            consumer_domain="grocery",
            agent_id="grocery-agent",
        )
        self.assertEqual(
            full.preferences["preferred_brand"].preference.provenance["service"],
            "authoritative-profile",
        )

    async def test_readonly_consumer_cannot_submit_candidates(self) -> None:
        platform, _, _, _ = build_platform()

        with self.assertRaisesRegex(PermissionError, "lacks capability submit_candidates"):
            await platform.submit_preference(
                candidate=self.candidate(
                    "allow_substitutions", "grocery", PreferenceScope.SESSION, True
                ),
                consumer_domain="grocery",
                agent_id="grocery-readonly-agent",
            )


class FinalScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_grocery_context(self) -> None:
        catalog = PreferenceCatalog.default()
        session = InMemorySessionAdapter()
        memory_value = preference(
            "grocery.banana_ripeness",
            "slightly_green",
            PreferenceSource.DYNAMIC_MEMORY,
            "grocery",
            confidence=0.94,
            provenance={"memory_name": "dynamic-banana"},
        )
        memory = InMemoryLongTermMemoryAdapter(
            [("U123", "shared-memory-test", memory_value)]
        )
        platform, _, _, _ = build_platform(
            session_backend=session,
            profile_adapter=MockProfileAdapter(catalog),
            dynamic_backend=memory,
        )
        await session.save_session_preference(
            "U123",
            "S456",
            preference(
                "grocery.allow_substitutions",
                True,
                PreferenceSource.SESSION_OVERRIDE,
                "grocery",
            ),
        )
        context = await platform.get_effective_context(
            user_id="U123",
            session_id="S456",
            consumer_domain="grocery",
            agent_id="grocery-agent",
            use_snapshot=False,
        )
        expected = {
            "preferred_store": ("Store-084", "customer"),
            "preferred_product_type": ("organic", "grocery"),
            "preferred_window": ("6PM-8PM", "delivery"),
            "banana_ripeness": ("slightly_green", "grocery"),
            "allow_substitutions": (True, "grocery"),
        }
        for key, (value, owner) in expected.items():
            self.assertEqual(context.preferences[key].preference.value, value)
            self.assertEqual(context.preferences[key].preference.owner_domain, owner)
        self.assertEqual(
            context.preferences["allow_substitutions"].preference.source,
            PreferenceSource.SESSION_OVERRIDE,
        )


if __name__ == "__main__":
    unittest.main()
