from __future__ import annotations

from types import SimpleNamespace

from app.shared_memory.adapters.memory_profile_adapter import (
    AgentPlatformMemoryProfileAdapter,
)
from app.shared_memory.catalog import PreferenceCatalog


def profile(**values: object) -> SimpleNamespace:
    return SimpleNamespace(profile=values)


def registry() -> dict[str, dict[str, object]]:
    return {
        "customer-preferences-v1": {
            "owner_domain": "customer",
            "fields": {"fruit": "customer.fruit"},
        },
        "grocery-preferences-v1": {
            "owner_domain": "grocery",
            "fields": {
                "preferred_product_type": "grocery.preferred_product_type",
                "preferred_snack": "grocery.preferred_snack",
            },
        },
        "store-preferences-v1": {
            "owner_domain": "store",
            "fields": {"preferred_product_type": "store.preferred_product_type"},
        },
    }


def test_grocery_scope_rejects_customer_and_store_profiles() -> None:
    adapter = AgentPlatformMemoryProfileAdapter(
        PreferenceCatalog.default(), profile_registry=registry()
    )
    response = SimpleNamespace(
        profiles={
            "store-preferences-v1": profile(preferred_product_type="mango chips"),
            "customer-preferences-v1": profile(fruit="Mango"),
            "grocery-preferences-v1": profile(preferred_snack="mango chips"),
        }
    )

    preferences = adapter._normalize_response("grocery", response)

    assert [(item.key, item.value, item.owner_domain) for item in preferences] == [
        ("grocery.preferred_snack", "mango chips", "grocery")
    ]


def test_schema_registry_selects_domain_specific_key_before_global_aliases() -> None:
    adapter = AgentPlatformMemoryProfileAdapter(
        PreferenceCatalog.default(), profile_registry=registry()
    )
    response = SimpleNamespace(
        profiles={
            "store-preferences-v1": profile(preferred_product_type="conventional")
        }
    )

    preferences = adapter._normalize_response("store", response)

    assert len(preferences) == 1
    assert preferences[0].key == "store.preferred_product_type"
    assert preferences[0].owner_domain == "store"


def test_unknown_schema_and_unknown_profile_field_fail_closed() -> None:
    adapter = AgentPlatformMemoryProfileAdapter(
        PreferenceCatalog.default(), profile_registry=registry()
    )
    response = SimpleNamespace(
        profiles={
            "unregistered-schema-v1": profile(preferred_snack="chips"),
            "grocery-preferences-v1": profile(undeclared_field="chips"),
        }
    )

    assert adapter._normalize_response("grocery", response) == []


def test_registry_mapping_cannot_cross_catalog_owner_boundary() -> None:
    invalid_registry = registry()
    invalid_registry["grocery-preferences-v1"]["fields"] = {
        "fruit": "customer.fruit"
    }
    adapter = AgentPlatformMemoryProfileAdapter(
        PreferenceCatalog.default(), profile_registry=invalid_registry
    )
    response = SimpleNamespace(
        profiles={"grocery-preferences-v1": profile(fruit="Mango")}
    )

    assert adapter._normalize_response("grocery", response) == []
