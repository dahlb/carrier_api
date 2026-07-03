"""Tests for entry-level (Smart Thermostat) model parsing and serialization."""

from copy import deepcopy
from typing import Any

from carrier_api import EntryLevelSystem, EntryLevelZone

SAMPLE_SYSTEM: dict[str, Any] = {
    "serial": "SERIALXXX",
    "name": "Basement",
    "location_id": "LOCATIONXXX",
    "model": "TSTATCCEEF-01",
    "firmware": "1.0.0",
    "temp_unit_format": "F",
    "connection": {"isConnected": True, "deviceId": "DEVICEXXX"},
    "zones": [
        {
            "index": 0,
            "mode": "cool",
            "rt": 75,
            "rh": 52,
            "clsp": {"current": 77, "min": 60},
            "htsp": {"current": 62, "max": 90},
            "fan_mode": "auto",
            "schedule_enabled": True,
            "hold_end_time": 0,
            "hold_countdown": 45,
            "stage_status": "Idle",
            "outside_temp": 97,
        }
    ],
}


def test_entry_level_system_parsing_and_serialization() -> None:
    """Parse a system payload and serialize identity, connection, and zones."""
    system = EntryLevelSystem(SAMPLE_SYSTEM)

    assert system.serial == "SERIALXXX"
    assert system.name == "Basement"
    assert system.model == "TSTATCCEEF-01"
    assert system.is_connected is True
    assert system.device_id == "DEVICEXXX"
    assert len(system.zones) == 1

    zone = system.zones[0]
    assert zone.index == 0
    assert zone.mode == "cool"
    assert zone.temperature == 75.0
    assert zone.humidity == 52
    assert zone.cool_set_point == 77.0
    assert zone.heat_set_point == 62.0
    assert zone.fan_mode == "auto"
    assert zone.on_hold is False

    assert system.as_dict()["zones"][0]["cool_set_point"] == 77.0
    assert repr(system) == str(system.as_dict())
    assert str(zone) == str(zone.as_dict())


def test_entry_level_zone_on_hold_when_schedule_disabled() -> None:
    """Report a hold when the zone's schedule is disabled."""
    raw = deepcopy(SAMPLE_SYSTEM["zones"][0])
    raw["schedule_enabled"] = False
    assert EntryLevelZone(raw).on_hold is True


def test_entry_level_system_without_zones() -> None:
    """Tolerate a system payload that omits zones."""
    raw = deepcopy(SAMPLE_SYSTEM)
    del raw["zones"]
    assert EntryLevelSystem(raw).zones == []
