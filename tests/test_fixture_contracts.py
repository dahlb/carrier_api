"""Contract tests for stored GraphQL and websocket fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest

from carrier_api import Config, Energy, Profile, Status, WebsocketDataUpdater
from carrier_api.system import System

FIXTURE_ROOT = Path(__file__).parent
GRAPHQL_FIXTURES = sorted((FIXTURE_ROOT / "graphql").glob("*.json"))
MESSAGE_FIXTURES = sorted((FIXTURE_ROOT / "messages").glob("*.json"))


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON fixture and assert that it contains an object.

    Args:
        path: Fixture path to load.

    Returns:
        Parsed JSON object.

    Raises:
        TypeError: If the fixture does not contain a JSON object.
    """
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return payload


@pytest.mark.parametrize("fixture_path", GRAPHQL_FIXTURES, ids=lambda path: path.name)
def test_graphql_fixtures_match_model_constructor_contracts(fixture_path: Path) -> None:
    """Ensure stored GraphQL fixtures still build the expected model objects.

    Args:
        fixture_path: Stored GraphQL fixture under test.
    """
    payload = load_json_object(fixture_path)

    match fixture_path.name:
        case "systems.json":
            systems_payload = payload["infinitySystems"]
            assert isinstance(systems_payload, list)
            for system_payload in systems_payload:
                profile = Profile(system_payload["profile"])
                status = Status(system_payload["status"])
                config = Config(system_payload["config"])

                assert profile.as_dict()["serial"]
                assert status.as_dict()["zones"]
                assert config.as_dict()["zones"]
        case "energy.json":
            energy = Energy(payload["infinityEnergy"])

            assert energy.as_dict()["periods"]
            assert energy.current_year_measurements() is not None
        case _:
            raise AssertionError(f"Unhandled GraphQL fixture: {fixture_path.name}")


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_path", MESSAGE_FIXTURES, ids=lambda path: path.name)
async def test_websocket_message_fixtures_match_update_handler_contract(
    fixture_path: Path,
    systems: list[System],
) -> None:
    """Ensure every stored websocket fixture can be handled by current models.

    Args:
        fixture_path: Stored websocket message fixture under test.
        systems: Fresh system models built from GraphQL fixtures.
    """
    message = fixture_path.read_text()
    payload = load_json_object(fixture_path)
    updater = WebsocketDataUpdater(systems)
    original_status_payload = systems[0].status.as_dict()
    original_config_payload = systems[0].config.as_dict()

    await updater.message_handler(message)

    if payload.get("deviceId") is None:
        assert systems[0].status.as_dict() == original_status_payload
        assert systems[0].config.as_dict() == original_config_payload
        return

    assert systems[0].as_dict()["profile"]["serial"] == payload["deviceId"]
    assert systems[0].status.as_dict()["zones"]
    assert systems[0].config.as_dict()["zones"]
