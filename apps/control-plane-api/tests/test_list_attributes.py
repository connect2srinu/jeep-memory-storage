from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from control_plane_api.application import create_app
from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.domain.memory import apply_list_op
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.persistence import Database
from control_plane_api.services.runtime_service import _coerce_value
from db_seed import seed_control_plane
from test_guided_setup import PLATFORM, setup_payload

AGENT = {"X-Agent-ID": "rewards-assistant"}
SCOPE = {"userId": "list-user", "appName": "rewards-demo", "domain": "rewards"}


def test_apply_list_op_adds_once_and_removes_ignoring_case() -> None:
    items = apply_list_op(None, "Simple Truth", "add")
    items = apply_list_op(items, "simple truth ", "add")
    items = apply_list_op(items, "Chobani", "add")
    assert items == ["Simple Truth", "Chobani"]
    assert apply_list_op(items, "CHOBANI", "remove") == ["Simple Truth"]
    # A value saved before the attribute became a list is kept as its first item.
    assert apply_list_op("Horizon", "Chobani", "add") == ["Horizon", "Chobani"]


def test_typed_attributes_are_stored_as_json_types_not_text() -> None:
    assert _coerce_value("True", "boolean", "x") is True
    assert _coerce_value("no", "boolean", "x") is False
    assert _coerce_value("$1,150", "number", "x") == 1150
    assert _coerce_value("12.5", "number", "x") == 12.5
    assert _coerce_value("4", "integer", "x") == 4
    assert _coerce_value("vegan", "string", "x") == "vegan"
    for value, data_type in (("maybe", "boolean"), ("lots", "number"), ("2.5", "integer")):
        with pytest.raises(ValueError):
            _coerce_value(value, data_type, "x")


@pytest.mark.asyncio
async def test_list_attribute_adds_and_removes_one_item_per_save(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'lists.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused", auth_enabled=False, google_id_token_audience=None
        ),
        database=database,
        store=MockMemoryStore(),
    )
    payload = setup_payload()
    payload["selectedPreferences"] = ["rewards.reward_type", "rewards.brands"]
    payload["customPreferences"].append(  # type: ignore[union-attr]
        {
            "attributeId": "rewards.brands",
            "displayName": "Brands",
            "description": "Brands the customer prefers",
            "dataType": "list",
            "allowedValues": [],
            "sensitivity": "normal",
        }
    )

    async def save(attribute: str, value: object, **extra: object) -> httpx.Response:
        return await client.put(
            f"/api/v1/runtime/preferences/{attribute}",
            headers=AGENT,
            json={"scope": SCOPE, "value": value, **extra},
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        preview = await client.post(
            "/api/v1/admin/memory-setups/preview", headers=PLATFORM, json=payload
        )
        assert preview.status_code == 200, preview.text
        activated = await client.post(
            "/api/v1/admin/memory-setups/activate", headers=PLATFORM, json=payload
        )
        assert activated.status_code == 201, activated.text

        for value in ("Simple Truth", "Chobani", "simple truth"):
            saved = await save("rewards.brands", value)
            assert saved.status_code == 200, saved.text
        removed = await save("rewards.brands", "chobani", remove=True)
        assert removed.status_code == 200, removed.text
        assert (await save("rewards.brands", ["Oatly"])).status_code == 400
        assert (await save("rewards.reward_type", "points", remove=True)).status_code == 400

        resolved = await client.post(
            "/api/v1/runtime/preferences/resolve",
            headers=AGENT,
            json={"scope": SCOPE, "sessionId": "list-session"},
        )
        assert resolved.status_code == 200, resolved.text
        snapshot = resolved.json()
        assert snapshot["preferences"]["brands"]["value"] == ["Simple Truth"]
        details = {item["attribute"]: item for item in snapshot["writablePreferenceDetails"]}
        assert details["rewards.brands"]["dataType"] == "list"
        assert details["rewards.reward_type"]["dataType"] == "string"
    await database.dispose()
