from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from app.shared_memory.auth import ConsumerCapability, ConsumerRegistry
from app.shared_memory.contracts import (
    ContractValidationError,
    compile_contracts,
    load_contracts,
)
from scripts.deploy import memory_profile_context_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = PROJECT_ROOT / "config" / "contracts"


def test_example_contracts_validate_and_compile_deterministically() -> None:
    bundle = load_contracts(CONTRACTS_DIR)
    compilation = compile_contracts(bundle)

    assert len(bundle.domains) == 6
    preference_keys = {
        preference.key
        for catalog in bundle.catalogs
        for preference in catalog.preferences
    }
    assert {"customer.fruit", "grocery.preferred_snack"} <= preference_keys
    assert compilation.differences(PROJECT_ROOT) == []


def test_compiled_memory_profiles_are_per_domain_and_sdk_compatible() -> None:
    from agentplatform import types

    context_spec = memory_profile_context_spec()
    validated = types.ReasoningEngineContextSpec.model_validate(context_spec)
    schema_configs = validated.memory_bank_config.structured_memory_configs[0].schema_configs

    assert {item.id for item in schema_configs} == {
        "customer-preferences-v1",
        "delivery-preferences-v1",
        "grocery-preferences-v1",
        "inventory-preferences-v1",
        "store-preferences-v1",
    }

    payload = json.loads(
        (PROJECT_ROOT / "app/shared_memory/profiles/memory_profiles.json").read_text(
            encoding="utf-8"
        )
    )
    registry = payload["profile_registry"]
    assert registry["customer-preferences-v1"]["fields"]["fruit"] == "customer.fruit"
    assert (
        registry["grocery-preferences-v1"]["fields"]["preferred_snack"]
        == "grocery.preferred_snack"
    )


def test_cross_domain_consumer_reference_is_rejected(tmp_path: Path) -> None:
    copied = tmp_path / "contracts"
    shutil.copytree(CONTRACTS_DIR, copied)
    consumer_path = copied / "grocery" / "consumers.yaml"
    payload = yaml.safe_load(consumer_path.read_text(encoding="utf-8"))
    payload["consumers"][0]["requiredPreferences"].append("pharmacy.medication")
    consumer_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractValidationError, match="unknown preference"):
        load_contracts(copied)


def test_generated_consumer_registry_documents_capabilities() -> None:
    payload = json.loads(
        (PROJECT_ROOT / "app/shared_memory/contracts/consumers.json").read_text(
            encoding="utf-8"
        )
    )
    grocery = payload["consumers"]["grocery-agent"]

    assert grocery["consumer_domain"] == "grocery"
    assert grocery["capabilities"] == {
        "administer_memory": False,
        "inspect_provenance": True,
        "resolve_context": True,
        "submit_candidates": True,
    }


def test_consumer_registry_enforces_operation_and_domain() -> None:
    registry = ConsumerRegistry.default()

    registration = registry.require(
        "grocery-agent", "grocery", ConsumerCapability.RESOLVE_CONTEXT
    )
    assert registration.consumer_domain == "grocery"
    with pytest.raises(PermissionError, match="lacks capability"):
        registry.require(
            "grocery-agent", "grocery", ConsumerCapability.ADMINISTER_MEMORY
        )
    with pytest.raises(PermissionError, match="does not match"):
        registry.require("grocery-agent", "delivery", ConsumerCapability.RESOLVE_CONTEXT)
