"""Tests for merging Carrier websocket updates into loaded system models."""

import json
from pathlib import Path
from typing import Any

import pytest

from carrier_api import (
    ActivityTypes,
    Config,
    Energy,
    FanModes,
    Profile,
    Status,
    System,
    WebsocketDataUpdater,
)
from carrier_api.api_websocket_data_updater import find_by_id

FIXTURE_ROOT = Path(__file__).parent


@pytest.fixture
def system_response() -> dict[str, Any]:
    """Load the GraphQL systems fixture.

    Returns:
        The parsed systems response fixture.
    """
    response = json.loads((FIXTURE_ROOT / "graphql/systems.json").read_text())
    if not isinstance(response, dict):
        raise TypeError("systems fixture must contain a JSON object")
    return response


@pytest.fixture
def energy_response() -> dict[str, Any]:
    """Load the GraphQL energy fixture.

    Returns:
        The parsed energy response fixture.
    """
    response = json.loads((FIXTURE_ROOT / "graphql/energy.json").read_text())
    if not isinstance(response, dict):
        raise TypeError("energy fixture must contain a JSON object")
    return response


@pytest.fixture
def systems(system_response: dict[str, Any], energy_response: dict[str, Any]) -> list[System]:
    """Build Carrier systems from stored API fixtures.

    Args:
        system_response: The parsed systems response fixture.
        energy_response: The parsed energy response fixture.

    Returns:
        Carrier systems built from the fixture responses.
    """
    prepared_systems: list[System] = []
    for single_system_response in system_response["infinitySystems"]:
        profile = Profile(raw=single_system_response["profile"])
        status = Status(raw=single_system_response["status"])
        config = Config(raw=single_system_response["config"])
        energy = Energy(raw=energy_response["infinityEnergy"])
        prepared_systems.append(
            System(profile=profile, status=status, config=config, energy=energy)
        )
    return prepared_systems


@pytest.fixture
def data_updater(systems: list[System]) -> WebsocketDataUpdater:
    """Build a websocket data updater for the prepared systems.

    Args:
        systems: Carrier systems built from fixture responses.

    Returns:
        A websocket data updater using the prepared systems.
    """
    return WebsocketDataUpdater(systems)


@pytest.fixture
def carrier_system(systems: list[System]) -> System:
    """Return the primary Carrier system under test.

    Args:
        systems: Carrier systems built from fixture responses.

    Returns:
        The first Carrier system from the fixtures.
    """
    return systems[0]


@pytest.fixture
def websocket_message_str(request: pytest.FixtureRequest) -> str:
    """Load a websocket message fixture selected by the test.

    Args:
        request: The pytest fixture request containing the message path parameter.

    Returns:
        The raw websocket message fixture contents.
    """
    message_path = request.param
    if not isinstance(message_path, str):
        raise TypeError("websocket message fixture parameter must be a string")
    return (FIXTURE_ROOT / message_path).read_text()


def test_find_by_id_error_message_omits_collection() -> None:
    """Raise a concise formatted error when no collection item matches."""
    collection = [{"id": "1", "name": "Zone 1"}]

    with pytest.raises(ValueError) as error:
        find_by_id(collection, "2")

    assert str(error.value) == "id: 2 not found in collection"
    assert error.value.args == ("id: 2 not found in collection",)


def test_carrier_system_error_message_is_formatted(
    data_updater: WebsocketDataUpdater,
) -> None:
    """Raise a formatted error when no loaded system matches a serial number.

    Args:
        data_updater: A websocket data updater built from fixture systems.
    """
    with pytest.raises(ValueError) as error:
        data_updater.carrier_system(serial_id="missing-serial")

    assert str(error.value) == "No carrier_system found for serial missing-serial"
    assert error.value.args == ("No carrier_system found for serial missing-serial",)


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket_message_str", ["messages/status_idu_cfm.json"], indirect=True)
async def test_status_idu_cfm_setup(
    system_response: dict[str, Any],
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Verify the base fixture state used before applying an IDU CFM message.

    Args:
        system_response: Parsed GraphQL system fixture.
        carrier_system: Prepared system model built from the fixture.
        websocket_message_str: Raw IDU CFM websocket message fixture.
    """
    assert carrier_system.status.raw == system_response["infinitySystems"][0]["status"]
    assert websocket_message_str


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket_message_str", ["messages/status_idu_cfm.json"], indirect=True)
async def test_status_idu_cfm_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply an IDU CFM status message and rebuild the status model.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw IDU CFM websocket message fixture.
    """
    assert carrier_system.status.airflow_cfm == 1239
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.airflow_cfm == 525
    assert Status(raw=carrier_system.status.raw).airflow_cfm == 525


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_message_str", ["messages/status_odu_opmode.json"], indirect=True
)
async def test_status_odu_opmode_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply an ODU operating mode status message without losing status state.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw ODU operating mode websocket message fixture.
    """
    assert carrier_system.status.mode == "heat"
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.mode == "heat"
    assert Status(raw=carrier_system.status.raw).mode == "heat"


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket_message_str", ["messages/status_zone_rh.json"], indirect=True)
async def test_status_zone_rh_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone humidity status message to the matching zone.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone humidity websocket message fixture.
    """
    assert carrier_system.status.zones[0].humidity == 32
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.zones[0].humidity == 34
    assert Status(raw=carrier_system.status.raw).zones[0].humidity == 34


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_message_str", ["messages/status_zone_conditioning.json"], indirect=True
)
async def test_status_zone_conditioning_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone conditioning status message and preserve parseability.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone conditioning websocket message fixture.
    """
    assert carrier_system.status.zones[0].conditioning == "active_heat"
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.zones[0].conditioning == "idle"
    assert Status(raw=carrier_system.status.raw).zones[0].conditioning == "idle"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_message_str", ["messages/status_zone_activity.json"], indirect=True
)
async def test_status_zone_activity_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone activity status message with set point changes.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone activity websocket message fixture.
    """
    assert carrier_system.status.zones[0].current_status_activity == ActivityTypes.WAKE
    assert carrier_system.status.zones[0].heat_set_point == 74
    assert carrier_system.status.zones[0].cool_set_point == 78
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.zones[0].current_status_activity == ActivityTypes.HOME
    assert carrier_system.status.zones[0].heat_set_point == 77
    assert carrier_system.status.zones[0].cool_set_point == 79
    reprocessed_status = Status(raw=carrier_system.status.raw)
    assert reprocessed_status.zones[0].current_status_activity == ActivityTypes.HOME
    assert reprocessed_status.zones[0].heat_set_point == 77
    assert reprocessed_status.zones[0].cool_set_point == 79


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_message_str", ["messages/status_zone_activity_only.json"], indirect=True
)
async def test_status_zone_activity_only_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone activity-only message while preserving unrelated fan state.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw activity-only websocket message fixture.
    """
    assert carrier_system.status.zones[0].current_status_activity == ActivityTypes.WAKE
    assert carrier_system.status.zones[0].fan == FanModes.MED
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.zones[0].current_status_activity == ActivityTypes.SLEEP
    assert carrier_system.status.zones[0].fan == FanModes.MED
    reprocessed_status = Status(raw=carrier_system.status.raw)
    assert reprocessed_status.zones[0].current_status_activity == ActivityTypes.SLEEP
    assert carrier_system.status.zones[0].fan == FanModes.MED


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket_message_str", ["messages/status_zone_hold.json"], indirect=True)
async def test_status_zone_hold_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone hold status message that moves the zone to manual activity.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone hold websocket message fixture.
    """
    assert carrier_system.status.zones[0].current_status_activity == ActivityTypes.WAKE
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.zones[0].current_status_activity == ActivityTypes.MANUAL
    reprocessed_status = Status(raw=carrier_system.status.raw)
    assert reprocessed_status.zones[0].current_status_activity == ActivityTypes.MANUAL


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket_message_str", ["messages/status_zone_htsp.json"], indirect=True)
async def test_status_zone_htsp_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply zone heat and cool set point changes from a status message.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone set point websocket message fixture.
    """
    assert carrier_system.status.zones[0].heat_set_point == 74
    assert carrier_system.status.zones[0].cool_set_point == 78
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.status.zones[0].heat_set_point == 72
    assert carrier_system.status.zones[0].cool_set_point == 85
    reprocessed_status = Status(raw=carrier_system.status.raw)
    assert reprocessed_status.zones[0].heat_set_point == 72
    assert reprocessed_status.zones[0].cool_set_point == 85


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket_message_str", ["messages/config_zone_hold.json"], indirect=True)
async def test_config_zone_hold_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone hold config message and rebuild the config model.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone hold config websocket message fixture.
    """
    assert carrier_system.config.zones[0].hold_activity is None
    await data_updater.message_handler(websocket_message_str)
    assert carrier_system.config.zones[0].hold_activity == ActivityTypes.MANUAL
    reprocessed_config = Config(raw=carrier_system.config.raw)
    assert reprocessed_config.zones[0].hold_activity == ActivityTypes.MANUAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_message_str", ["messages/config_zone_program.json"], indirect=True
)
async def test_config_zone_program_message_handler(
    data_updater: WebsocketDataUpdater,
    carrier_system: System,
    websocket_message_str: str,
) -> None:
    """Apply a zone program config message without corrupting schedule data.

    Args:
        data_updater: Websocket updater under test.
        carrier_system: Prepared system model that receives the update.
        websocket_message_str: Raw zone program config websocket message fixture.
    """
    await data_updater.message_handler(websocket_message_str)
    reprocessed_config = Config(raw=carrier_system.config.raw)
    assert carrier_system.config.zones[0].program_json == reprocessed_config.zones[0].program_json


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "websocket_message_str", ["messages/heartbeat_with_no_device_id.json"], indirect=True
)
async def test_heartbeat_with_no_device_id_message_handler(
    data_updater: WebsocketDataUpdater,
    websocket_message_str: str,
) -> None:
    """Ignore a heartbeat message that does not identify a Carrier device.

    Args:
        data_updater: Websocket updater under test.
        websocket_message_str: Raw heartbeat websocket message fixture.
    """
    await data_updater.message_handler(websocket_message_str)
