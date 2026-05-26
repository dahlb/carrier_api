"""Tests for Carrier model serialization and branch behavior."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from carrier_api import Config, Energy, Profile, Status, System
from carrier_api.config import ConfigZone, ConfigZoneActivity, active_schedule_periods
from carrier_api.const import ActivityTypes, FanModes, SystemModes
from carrier_api.status import StatusZone
from carrier_api.util import safely_get_json_value


def test_profile_as_dict_and_string_representations(system_response: dict[str, Any]) -> None:
    """Serialize profile identity and equipment metadata.

    Args:
        system_response: Parsed systems fixture.
    """
    profile = Profile(system_response["infinitySystems"][0]["profile"])

    assert profile.as_dict() == {
        "name": "HVAC",
        "serial": "SERIALXXX",
        "model": "SYSTXCCWIC01-B",
        "brand": "Carrier",
        "firmware": "CESR131626-04.70",
        "indoor_model": "59TN6A100V211122",
        "indoor_serial": "SERIALXXXX",
        "indoor_unit_type": "furnace",
        "indoor_unit_source": "gas",
        "outdoor_model": "24ANB736A00310",
        "outdoor_serial": "SERIALXXXXX",
        "outdoor_unit_type": "ac2stg",
    }
    assert repr(profile) == str(profile.as_dict())
    assert str(profile) == str(profile.as_dict())


def test_energy_as_dict_current_year_and_missing_year(
    energy_response: dict[str, Any],
) -> None:
    """Serialize energy payloads and handle missing current-year measurements.

    Args:
        energy_response: Parsed energy fixture.
    """
    energy = Energy(energy_response["infinityEnergy"])
    energy_without_year = Energy(
        {
            **energy_response["infinityEnergy"],
            "energyPeriods": [
                period
                for period in energy_response["infinityEnergy"]["energyPeriods"]
                if period["energyPeriodType"] != "year1"
            ],
        }
    )

    current_year = energy.current_year_measurements()

    assert current_year is not None
    assert current_year.as_dict()["gas"] == 25905
    assert energy_without_year.current_year_measurements() is None
    assert energy.as_dict()["periods"][0]["id"] == "day1"
    assert repr(energy) == str(energy.as_dict())
    assert str(current_year) == str(current_year.as_dict())


def test_status_modes_zone_conditioning_and_serialization(
    system_response: dict[str, Any],
) -> None:
    """Cover status mode mappings, zone conditioning mappings, and serialization.

    Args:
        system_response: Parsed systems fixture.
    """
    raw_status = system_response["infinitySystems"][0]["status"]
    status = Status(raw_status)

    heat_status = Status({**raw_status, "mode": "gasheat"})

    assert heat_status.mode_const == SystemModes.HEAT
    assert status.zones[0].zone_conditioning_const == SystemModes.HEAT
    assert status.zones[0].current_status_activity == ActivityTypes.WAKE
    assert status.zones[0].current_activity == ActivityTypes.WAKE
    assert status.zones[0].as_dict()["current_activity"] == "wake"
    assert status.zones[0].as_dict()["current_status_activity"] == "wake"
    assert status.as_dict()["time_stamp"] == datetime(2025, 3, 3, 13, 42, 34, 328000, UTC)
    assert status.as_dict()["uv_lamp_level"] == 100
    assert repr(status.zones[0]) == str(status.zones[0].as_dict())

    cool_zone = StatusZone({**raw_status["zones"][0], "zoneconditioning": "active_cool"})
    idle_zone = StatusZone({**raw_status["zones"][0], "zoneconditioning": "idle"})
    unknown_zone = StatusZone({**raw_status["zones"][0], "zoneconditioning": "unknown"})
    cool_status = Status({**raw_status, "mode": "dehumidify"})
    unknown_status = Status({**raw_status, "mode": "fanonly"})

    assert cool_zone.zone_conditioning_const == SystemModes.COOL
    assert idle_zone.zone_conditioning_const == SystemModes.OFF
    assert cool_status.mode_const == SystemModes.COOL
    with pytest.raises(ValueError, match="Unknown conditioning: unknown"):
        _ = unknown_zone.zone_conditioning_const
    with pytest.raises(ValueError, match="Unknown mode: fanonly"):
        _ = unknown_status.mode_const


def test_config_schedule_branches_and_serialization(system_response: dict[str, Any]) -> None:
    """Cover config activity lookup, schedule branches, and serialization.

    Args:
        system_response: Parsed systems fixture.
    """
    raw_config = deepcopy(system_response["infinitySystems"][0]["config"])
    zone_json = raw_config["zones"][0]
    vacation_json = {
        "type": "vacation",
        "clsp": raw_config["vacmaxt"],
        "htsp": raw_config["vacmint"],
        "fan": raw_config["vacfan"],
    }
    zone = ConfigZone(zone_json, vacation_json)
    held_zone = ConfigZone({**zone_json, "hold": "on", "holdActivity": "manual"}, vacation_json)
    config = Config(raw_config)

    assert active_schedule_periods(
        [
            {"enabled": "off", "time": "00:00"},
            {"enabled": "on", "time": "08:00"},
        ]
    ) == [{"enabled": "on", "time": "08:00"}]
    assert isinstance(zone.find_activity(ActivityTypes.HOME), ConfigZoneActivity)
    assert zone.find_activity(ActivityTypes.VACATION) is not None
    assert zone.find_activity(ActivityTypes.MANUAL) is not None
    assert zone.today_active_periods()
    assert zone.yesterday_active_periods()
    assert zone.current_scheduled_activity() is not None
    assert zone.current_activity() is zone.current_scheduled_activity()
    assert held_zone.current_scheduled_activity() is held_zone.find_activity(ActivityTypes.MANUAL)
    assert zone.next_activity_time() is not None
    assert config.humidifier_heat_target == 35
    assert config.as_dict()["zones"][0]["activities"][-1]["type"] == "vacation"
    assert config.as_dict()["zones"][0]["current_activity"]["from_status"] is None
    assert repr(config) == str(config.as_dict())
    assert str(zone) == str(zone.as_dict())


def test_config_zone_current_activity_from_status_uses_api_reported_profile(
    system_response: dict[str, Any],
) -> None:
    """Resolve the current activity profile from Carrier status data.

    Args:
        system_response: Parsed systems fixture.
    """
    raw_system = system_response["infinitySystems"][0]
    config = Config(raw_system["config"])
    status = Status(raw_system["status"])
    zone = config.zones[0]
    status_zone = status.zones[0]

    current_status_activity = zone.current_status_activity(status_zone)

    assert current_status_activity is not None
    current_scheduled_activity = zone.current_scheduled_activity()
    assert current_scheduled_activity is not None
    assert current_status_activity.type == ActivityTypes.WAKE
    assert current_status_activity is zone.find_activity(ActivityTypes.WAKE)
    assert zone.as_dict(status_zone)["current_activity"] == {
        "from_schedule": current_scheduled_activity.as_dict(),
        "from_status": current_status_activity.as_dict(),
    }


def test_config_zone_current_activity_from_status_uses_status_when_config_hold_lags(
    system_response: dict[str, Any],
) -> None:
    """Resolve status activity from status data even when config hold state lags.

    Args:
        system_response: Parsed systems fixture.
    """
    raw_system = system_response["infinitySystems"][0]
    raw_config = deepcopy(raw_system["config"])
    raw_status = deepcopy(raw_system["status"])
    raw_config["zones"][0]["hold"] = "on"
    raw_config["zones"][0]["holdActivity"] = "manual"
    raw_status["zones"][0]["currentActivity"] = "wake"
    config = Config(raw_config)
    status = Status(raw_status)
    zone = config.zones[0]

    current_status_activity = zone.current_status_activity(status.zones[0])

    assert current_status_activity is not None
    assert current_status_activity.type == ActivityTypes.WAKE


def test_config_zone_current_activity_from_status_returns_none_for_missing_profile(
    system_response: dict[str, Any],
) -> None:
    """Return no profile when Carrier reports an activity not present in config.

    Args:
        system_response: Parsed systems fixture.
    """
    raw_system = system_response["infinitySystems"][0]
    raw_config = deepcopy(raw_system["config"])
    raw_status = deepcopy(raw_system["status"])
    raw_config["zones"][0]["activities"] = [
        activity for activity in raw_config["zones"][0]["activities"] if activity["type"] != "wake"
    ]
    config = Config(raw_config)
    status = Status(raw_status)

    assert config.zones[0].current_status_activity(status.zones[0]) is None


def test_config_next_activity_time_returns_none_when_today_and_tomorrow_are_disabled() -> None:
    """Return no next activity time when today and tomorrow have no enabled periods."""
    zone = ConfigZone(
        zone_json={
            "id": "1",
            "name": "Zone 1",
            "holdActivity": "home",
            "hold": "off",
            "otmr": None,
            "occEnabled": "off",
            "activities": [
                {
                    "type": "home",
                    "id": "1",
                    "fan": "low",
                    "htsp": "68",
                    "clsp": "72",
                }
            ],
            "program": {
                "day": [
                    {
                        "period": [
                            {
                                "enabled": "off",
                                "time": "00:00",
                                "activity": "home",
                            }
                        ]
                    }
                    for _ in range(7)
                ]
            },
        },
        vacation_json={
            "type": "vacation",
            "fan": None,
            "htsp": None,
            "clsp": None,
        },
    )

    assert zone.next_activity_time() is None


def test_system_as_dict_uses_nested_model_dictionaries(
    systems: list[System],
) -> None:
    """Serialize system aggregates with nested model dictionaries.

    Args:
        systems: Prepared system fixture models.
    """
    system = systems[0]

    assert system.as_dict()["profile"] == system.profile.as_dict()
    assert system.as_dict()["status"] == system.status.as_dict()
    assert system.as_dict()["config"] == system.config.as_dict(system.status.zones)
    assert system.as_dict()["energy"] == system.energy.as_dict()
    assert (
        system.as_dict()["config"]["zones"][0]["current_activity"]["from_status"]["type"] == "wake"
    )
    assert repr(system) == str(system.as_dict())


def test_system_reports_supported_hvac_capabilities_from_equipment_and_config(
    systems: list[System],
) -> None:
    """Expose supported heat, cool, and fan controls from best-known raw data.

    Args:
        systems: Prepared system fixture models.
    """
    system = systems[0]

    assert system.supports_heat()
    assert system.supports_cool()
    assert system.supports_fan()
    assert system.supported_hvac_capabilities() == {
        "heat": True,
        "cool": True,
        "fan": True,
    }
    assert system.as_dict()["supported_hvac_capabilities"] == {
        "heat": True,
        "cool": True,
        "fan": True,
    }


def test_safely_get_json_value_handles_nested_lists_none_and_cast_failures() -> None:
    """Resolve nested JSON paths and return None for unsupported paths or casts."""
    payload = {"items": [{"value": "42"}, {"value": "none"}, {"value": "bad"}]}

    assert safely_get_json_value(payload, "items.0.value", int) == 42
    assert safely_get_json_value(payload, "items.1.value", int) is None
    assert safely_get_json_value(payload, "items.2.value", int) is None
    assert safely_get_json_value(payload, "items.9.value") is None
    assert safely_get_json_value([], "missing") is None


def test_activity_and_fan_string_representations() -> None:
    """Serialize standalone config activity values."""
    activity = ConfigZoneActivity(
        {
            "type": "home",
            "id": "activity-1",
            "fan": "med",
            "htsp": "70",
            "clsp": "76",
        }
    )

    assert activity.type == ActivityTypes.HOME
    assert activity.fan == FanModes.MED
    assert activity.as_dict() == {
        "api_id": "activity-1",
        "type": "home",
        "fan": "med",
        "heat_set_point": 70.0,
        "cool_set_point": 76.0,
    }
    assert repr(activity) == str(activity.as_dict())
