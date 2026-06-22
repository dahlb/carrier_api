"""Tests for Carrier model serialization and branch behavior."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from carrier_api import (
    ENERGY_USAGE_METRIC_LABELS,
    Config,
    Energy,
    EnergyPeriod,
    EnergyUsageMetric,
    Profile,
    Status,
    System,
)
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


def test_energy_period_helpers_return_sensor_measurements(
    energy_response: dict[str, Any],
) -> None:
    """Look up sensor-facing energy values without raw payload access.

    Args:
        energy_response: Parsed energy fixture.
    """
    energy = Energy(energy_response["infinityEnergy"])

    daily = energy.measurement_for_period(EnergyPeriod.DAY_1)
    current_day = energy.current_day_measurements()
    monthly = energy.current_month_measurements()
    yearly = energy.current_year_measurements()

    assert daily is not None
    assert current_day is not None
    assert daily.as_dict() == current_day.as_dict()
    assert monthly is not None
    assert yearly is not None
    assert daily.value_for_metric(EnergyUsageMetric.GAS) == 397
    assert isinstance(daily.value_for_metric(EnergyUsageMetric.GAS), int)
    assert isinstance(daily.as_dict()["gas"], int)
    assert monthly.value_for_metric(EnergyUsageMetric.GAS) == 11012
    assert yearly.value_for_metric(EnergyUsageMetric.GAS) == 25905
    assert energy.value_for_period_metric(EnergyPeriod.DAY_1, EnergyUsageMetric.GAS) == 397
    assert energy.value_for_period_metric(EnergyPeriod.MONTH_1, "gas") == 11012
    assert energy.value_for_period_metric(EnergyPeriod.YEAR_1, "hp_heat") == 0
    assert energy.value_for_period_metric("missing", "gas") is None
    assert energy.value_for_period_metric(EnergyPeriod.YEAR_1, "unknown") is None
    assert yearly.value_for_metric("hp_heat") == 0
    assert yearly.value_for_metric("unknown") is None
    assert energy.measurement_for_period("missing") is None


def test_energy_measurements_preserve_fractional_usage_values(
    energy_response: dict[str, Any],
) -> None:
    """Preserve fractional Carrier energy readings for sensor consumers.

    Args:
        energy_response: Parsed energy fixture.
    """
    energy_payload = deepcopy(energy_response["infinityEnergy"])
    energy_payload["energyPeriods"][0]["coolingKwh"] = 0.9
    energy_payload["energyPeriods"][0]["gasKwh"] = 397.5

    energy = Energy(energy_payload)
    current_day = energy.current_day_measurements()

    assert current_day is not None
    assert current_day.cooling == 0.9
    assert isinstance(current_day.cooling, float)
    assert current_day.value_for_metric(EnergyUsageMetric.COOLING) == 0.9
    assert energy.value_for_period_metric(EnergyPeriod.DAY_1, EnergyUsageMetric.GAS) == 397.5
    assert current_day.as_dict()["cooling"] == 0.9


@pytest.mark.parametrize("invalid_value", ["nan", "inf", "1e999"])
def test_energy_measurements_reject_non_finite_usage_values(
    energy_response: dict[str, Any],
    invalid_value: str,
) -> None:
    """Reject non-finite energy readings instead of leaking invalid floats.

    Args:
        energy_response: Parsed energy fixture.
        invalid_value: Invalid energy value to parse.
    """
    energy_payload = deepcopy(energy_response["infinityEnergy"])
    energy_payload["energyPeriods"][0]["gasKwh"] = invalid_value

    energy = Energy(energy_payload)
    current_day = energy.current_day_measurements()

    assert current_day is not None
    assert current_day.gas is None
    assert current_day.value_for_metric(EnergyUsageMetric.GAS) is None
    assert current_day.as_dict()["gas"] is None


def test_energy_measurement_missing_metric_attribute_returns_none(
    energy_response: dict[str, Any],
) -> None:
    """Return None when a normalized metric attribute is unavailable.

    Args:
        energy_response: Parsed energy fixture.
    """
    energy = Energy(energy_response["infinityEnergy"])
    current_day = energy.current_day_measurements()

    assert current_day is not None
    del current_day.gas

    assert current_day.value_for_metric(EnergyUsageMetric.GAS) is None


def test_energy_enabled_usage_metrics_use_api_metric_vocabulary(
    energy_response: dict[str, Any],
) -> None:
    """Expose enabled usage metrics without caller-owned raw field maps.

    Args:
        energy_response: Parsed energy fixture.
    """
    energy = Energy(energy_response["infinityEnergy"])

    assert energy.enabled_usage_metrics() == (
        EnergyUsageMetric.COOLING,
        EnergyUsageMetric.GAS,
    )
    assert energy.is_usage_metric_enabled(EnergyUsageMetric.COOLING) is True
    assert energy.is_usage_metric_enabled("gas") is True
    assert energy.is_usage_metric_enabled(EnergyUsageMetric.ELECTRIC_HEAT) is False
    assert energy.is_usage_metric_enabled("unknown") is False


def test_energy_usage_metrics_expose_display_labels() -> None:
    """Expose human-readable labels for sensor names."""
    assert ENERGY_USAGE_METRIC_LABELS == {
        EnergyUsageMetric.COOLING: "Cooling",
        EnergyUsageMetric.ELECTRIC_HEAT: "Electric Heat",
        EnergyUsageMetric.FAN_GAS: "Fan Gas",
        EnergyUsageMetric.FAN: "Fan",
        EnergyUsageMetric.GAS: "Gas",
        EnergyUsageMetric.HP_HEAT: "Heat Pump Heat",
        EnergyUsageMetric.LOOP_PUMP: "Loop Pump",
        EnergyUsageMetric.REHEAT: "Reheat",
    }
    assert {metric.value: metric.label for metric in EnergyUsageMetric} == {
        "cooling": "Cooling",
        "hp_heat": "Heat Pump Heat",
        "fan": "Fan",
        "electric_heat": "Electric Heat",
        "reheat": "Reheat",
        "fan_gas": "Fan Gas",
        "gas": "Gas",
        "loop_pump": "Loop Pump",
    }


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
    assert status.zones[0].current_status_activity_type == ActivityTypes.WAKE
    assert status.zones[0].current_activity == ActivityTypes.WAKE
    assert status.zones[0].as_dict()["current_status_activity_type"] == "wake"
    assert "current_activity" not in status.zones[0].as_dict()
    status.zones[0].current_activity = ActivityTypes.HOME
    assert status.zones[0].current_status_activity_type == ActivityTypes.HOME
    assert status.as_dict()["time_stamp"] == datetime(2025, 3, 3, 13, 42, 34, 328000, UTC)
    assert status.as_dict()["uv_lamp_level"] == 100
    assert status.outdoor_unit is not None
    assert status.outdoor_unit.as_dict() == {
        "type": "ac2stgeverest",
        "operational_status": "off",
    }
    idu_without_airflow = {key: value for key, value in raw_status["idu"].items() if key != "cfm"}
    odu_with_airflow = Status(
        {
            **raw_status,
            "idu": idu_without_airflow,
            "odu": {**raw_status["odu"], "iducfm": "482"},
        }
    )
    assert odu_with_airflow.outdoor_unit is not None
    assert odu_with_airflow.outdoor_unit.airflow_cfm is None
    assert "airflow_cfm" not in odu_with_airflow.outdoor_unit.as_dict()
    assert odu_with_airflow.indoor_unit is not None
    assert odu_with_airflow.indoor_unit.airflow_cfm == 482
    assert odu_with_airflow.indoor_unit.as_dict()["airflow_cfm"] == 482
    assert odu_with_airflow.airflow_cfm == 482
    assert odu_with_airflow.as_dict()["airflow_cfm"] == 482
    assert status.indoor_unit is not None
    indoor_unit_data = status.indoor_unit.as_dict()
    assert indoor_unit_data == {
        "type": "furnace2stg",
        "operational_status": "low",
        "airflow_cfm": 1239,
        "static_pressure": pytest.approx(1.399999976158142),
        "blower_rpm": 1224,
    }
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


def test_config_zone_current_activity_from_status_returns_none_for_wrong_zone(
    system_response: dict[str, Any],
) -> None:
    """Return no profile when the supplied status belongs to another zone.

    Args:
        system_response: Parsed systems fixture.
    """
    raw_system = system_response["infinitySystems"][0]
    config = Config(raw_system["config"])
    wrong_status_zone = StatusZone(
        {
            **raw_system["status"]["zones"][0],
            "id": "2",
            "enabled": "on",
            "currentActivity": "wake",
        }
    )

    assert config.zones[0].current_status_activity(wrong_status_zone) is None
    assert config.zones[0].as_dict(wrong_status_zone)["current_activity"]["from_status"] is None


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


def test_system_hvac_capabilities_ignore_profile_equipment_strings(
    system_response: dict[str, Any],
    energy_response: dict[str, Any],
) -> None:
    """Avoid reporting support from unsupported profile strings.

    Args:
        system_response: Parsed systems fixture.
        energy_response: Parsed energy fixture.
    """
    raw_system = deepcopy(system_response["infinitySystems"][0])
    raw_system["profile"]["idutype"] = "unknown"
    raw_system["profile"]["idusource"] = "gas"
    raw_system["profile"]["odutype"] = "unknown"
    raw_system["config"]["cfgfan"] = "off"
    raw_energy = deepcopy(energy_response["infinityEnergy"])
    for energy_config in raw_energy["energyConfig"].values():
        if isinstance(energy_config, dict):
            energy_config["display"] = False
            energy_config["enabled"] = False
    system = System(
        Profile(raw_system["profile"]),
        Status(raw_system["status"]),
        Config(raw_system["config"]),
        Energy(raw_energy),
    )

    assert system.supported_hvac_capabilities() == {
        "heat": False,
        "cool": False,
        "fan": False,
    }


@pytest.mark.parametrize(
    ("outdoor_unit_type", "expected_capabilities"),
    [
        ("multistghp", {"heat": True, "cool": True, "fan": False}),
        ("MultiStgHp ", {"heat": True, "cool": True, "fan": False}),
        ("multistgac", {"heat": False, "cool": True, "fan": False}),
        ("ac2stg", {"heat": False, "cool": True, "fan": False}),
        ("AC2STG", {"heat": False, "cool": True, "fan": False}),
        ("varcaphp", {"heat": True, "cool": True, "fan": False}),
        ("ac1stg", {"heat": False, "cool": True, "fan": False}),
        ("varcapac", {"heat": False, "cool": True, "fan": False}),
    ],
)
def test_system_hvac_capabilities_use_known_outdoor_unit_types(
    system_response: dict[str, Any],
    energy_response: dict[str, Any],
    outdoor_unit_type: str,
    expected_capabilities: dict[str, bool],
) -> None:
    """Supplement energy flags with known outdoor unit capability hints.

    Args:
        system_response: Parsed systems fixture.
        energy_response: Parsed energy fixture.
        outdoor_unit_type: Outdoor unit type to test.
        expected_capabilities: Expected capability map for the equipment type.
    """
    raw_system = deepcopy(system_response["infinitySystems"][0])
    raw_system["profile"]["idutype"] = "unknown"
    raw_system["profile"]["odutype"] = outdoor_unit_type
    raw_system["config"]["cfgfan"] = "off"
    raw_energy = deepcopy(energy_response["infinityEnergy"])
    for energy_config in raw_energy["energyConfig"].values():
        if isinstance(energy_config, dict):
            energy_config["display"] = False
            energy_config["enabled"] = False
    system = System(
        Profile(raw_system["profile"]),
        Status(raw_system["status"]),
        Config(raw_system["config"]),
        Energy(raw_energy),
    )

    assert system.supported_hvac_capabilities() == expected_capabilities


@pytest.mark.parametrize(
    ("indoor_unit_type", "fan_enabled", "expected_capabilities"),
    [
        ("furnace", False, {"heat": True, "cool": False, "fan": False}),
        ("Furnace", False, {"heat": True, "cool": False, "fan": False}),
        ("furnace ", False, {"heat": True, "cool": False, "fan": False}),
        ("fancoil", None, {"heat": False, "cool": False, "fan": True}),
        ("Fancoil ", None, {"heat": False, "cool": False, "fan": True}),
    ],
)
def test_system_hvac_capabilities_use_known_indoor_unit_types(
    system_response: dict[str, Any],
    energy_response: dict[str, Any],
    indoor_unit_type: str,
    fan_enabled: bool | None,
    expected_capabilities: dict[str, bool],
) -> None:
    """Supplement energy flags with known indoor unit capability hints.

    Args:
        system_response: Parsed systems fixture.
        energy_response: Parsed energy fixture.
        indoor_unit_type: Indoor unit type to test.
        fan_enabled: Optional config fan flag override used to exercise fallback.
        expected_capabilities: Expected capability map for the equipment type.
    """
    raw_system = deepcopy(system_response["infinitySystems"][0])
    raw_system["profile"]["idutype"] = indoor_unit_type
    raw_system["profile"]["odutype"] = "unknown"
    raw_system["config"]["cfgfan"] = fan_enabled
    raw_energy = deepcopy(energy_response["infinityEnergy"])
    for energy_config in raw_energy["energyConfig"].values():
        if isinstance(energy_config, dict):
            energy_config["display"] = False
            energy_config["enabled"] = False
    system = System(
        Profile(raw_system["profile"]),
        Status(raw_system["status"]),
        Config(raw_system["config"]),
        Energy(raw_energy),
    )

    assert system.supported_hvac_capabilities() == expected_capabilities


def test_system_hvac_capabilities_do_not_let_activity_fan_override_cfgfan_off(
    systems: list[System],
) -> None:
    """Treat cfgfan as authoritative when Carrier provides that flag.

    Args:
        systems: Prepared system fixture models.
    """
    system = systems[0]
    system.config.fan_enabled = False
    system.energy.fan = True
    system.energy.fan_gas = True

    assert not system.supports_fan()
    assert not system.supported_hvac_capabilities()["fan"]


def test_system_hvac_capabilities_fall_back_to_energy_fan_flags(
    systems: list[System],
) -> None:
    """Use energy fan flags when cfgfan is absent.

    Args:
        systems: Prepared system fixture models.
    """
    system = systems[0]
    system.config.fan_enabled = None
    system.energy.fan = False
    system.energy.fan_gas = False

    assert not system.supports_fan()

    system.energy.fan = True

    assert system.supports_fan()
    assert system.supported_hvac_capabilities()["fan"]


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
