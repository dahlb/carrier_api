"""Shared pytest fixtures for Carrier API tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from carrier_api import Config, Energy, Profile, Status, System

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
