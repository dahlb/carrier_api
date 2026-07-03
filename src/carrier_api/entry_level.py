"""Models for Carrier "entry level" (Smart Thermostat) systems and zones.

These cover the non-Infinity Carrier Smart Thermostat line (e.g. TSTATCCEEF-01)
exposed by the cloud as ``entryLevelSystems``. They are a separate object type
from Infinity ``System``: single-zone, addressed by serial and zone index, with
cool/heat set points sent as a pair.
"""

from typing import Any

from .util import safely_get_json_value


class EntryLevelZone:
    """Runtime state and set points for one entry-level thermostat zone."""

    def __init__(self, raw: dict[str, Any]) -> None:
        """Build a zone from a Carrier ``entryLevelSystems`` zone payload.

        Args:
            raw: Raw zone object from the Carrier GraphQL response.
        """
        self.raw = raw
        self.index: int = safely_get_json_value(raw, "index", int)
        self.mode: str | None = safely_get_json_value(raw, "mode")
        self.temperature: float | None = safely_get_json_value(raw, "rt", float)
        self.humidity: int | None = safely_get_json_value(raw, "rh", int)
        self.cool_set_point: float | None = safely_get_json_value(raw, "clsp.current", float)
        self.cool_set_point_min: float | None = safely_get_json_value(raw, "clsp.min", float)
        self.heat_set_point: float | None = safely_get_json_value(raw, "htsp.current", float)
        self.heat_set_point_max: float | None = safely_get_json_value(raw, "htsp.max", float)
        self.fan_mode: str | None = safely_get_json_value(raw, "fan_mode")
        self.schedule_enabled: bool | None = safely_get_json_value(raw, "schedule_enabled")
        self.hold_end_time: int | None = safely_get_json_value(raw, "hold_end_time", int)
        self.hold_countdown: int | None = safely_get_json_value(raw, "hold_countdown", int)
        self.stage_status: str | None = safely_get_json_value(raw, "stage_status")
        self.outdoor_temperature: float | None = safely_get_json_value(raw, "outside_temp", float)

    @property
    def on_hold(self) -> bool:
        """Return whether the zone is held off its programmed schedule.

        Returns:
            ``True`` when scheduling is disabled (a manual hold is active).
        """
        return self.schedule_enabled is False

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the zone.

        Returns:
            A dictionary containing sensor values, set points, and hold state.
        """
        return {
            "index": self.index,
            "mode": self.mode,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "cool_set_point": self.cool_set_point,
            "heat_set_point": self.heat_set_point,
            "fan_mode": self.fan_mode,
            "schedule_enabled": self.schedule_enabled,
            "hold_end_time": self.hold_end_time,
            "stage_status": self.stage_status,
            "outdoor_temperature": self.outdoor_temperature,
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the zone.

        Returns:
            The zone dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the zone.

        Returns:
            The zone representation converted to a string.
        """
        return str(self.as_dict())


class EntryLevelSystem:
    """A Carrier entry-level (Smart Thermostat) system and its zones."""

    def __init__(self, raw: dict[str, Any]) -> None:
        """Build a system from a Carrier ``entryLevelSystems`` payload.

        Args:
            raw: Raw system object from the Carrier GraphQL response.
        """
        self.raw = raw
        self.serial: str = safely_get_json_value(raw, "serial")
        self.name: str | None = safely_get_json_value(raw, "name")
        self.model: str | None = safely_get_json_value(raw, "model")
        self.firmware: str | None = safely_get_json_value(raw, "firmware")
        self.location_id: str | None = safely_get_json_value(raw, "location_id")
        self.temperature_unit: str | None = safely_get_json_value(raw, "temp_unit_format")
        self.is_connected: bool | None = safely_get_json_value(raw, "connection.isConnected")
        self.device_id: str | None = safely_get_json_value(raw, "connection.deviceId")
        self.zones: list[EntryLevelZone] = [
            EntryLevelZone(zone_json) for zone_json in (safely_get_json_value(raw, "zones") or [])
        ]

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the system.

        Returns:
            A dictionary containing system identity, connection, and zone state.
        """
        return {
            "serial": self.serial,
            "name": self.name,
            "model": self.model,
            "firmware": self.firmware,
            "location_id": self.location_id,
            "temperature_unit": self.temperature_unit,
            "is_connected": self.is_connected,
            "zones": [zone.as_dict() for zone in self.zones],
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the system.

        Returns:
            The system dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the system.

        Returns:
            The system representation converted to a string.
        """
        return str(self.as_dict())
