"""Configuration models and schedule helpers for Carrier systems."""

from datetime import UTC, datetime
from logging import getLogger
from typing import Any

from .const import ActivityTypes, FanModes
from .util import safely_get_json_value

_LOGGER = getLogger(__name__)


def active_schedule_periods(periods_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter a Carrier schedule period list down to enabled periods.

    Args:
        periods_json: Raw period objects from a Carrier zone schedule day.

    Returns:
        A list containing only periods whose ``enabled`` value is ``"on"``.
    """
    return list(
        filter(lambda period: safely_get_json_value(period, "enabled") == "on", periods_json)
    )


class ConfigZoneActivity:
    """Configured set points and fan mode for a zone activity."""

    def __init__(self, zone_activity_json: dict[str, Any]) -> None:
        """Build a zone activity from Carrier configuration data.

        Args:
            zone_activity_json: Raw activity object from a zone configuration,
                including activity type, set points, and fan mode.
        """
        self.type: ActivityTypes = ActivityTypes(safely_get_json_value(zone_activity_json, "type"))
        self.api_id = safely_get_json_value(zone_activity_json, "id")
        self.fan: FanModes = FanModes(zone_activity_json["fan"])
        self.heat_set_point: float = safely_get_json_value(zone_activity_json, "htsp", float)
        self.cool_set_point: float = safely_get_json_value(zone_activity_json, "clsp", float)

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the activity configuration.

        Returns:
            A dictionary containing the activity identifier, type, fan mode, and
            configured heat and cool set points.
        """
        return {
            "api_id": self.api_id,
            "type": self.type.value,
            "fan": self.fan.value,
            "heat_set_point": self.heat_set_point,
            "cool_set_point": self.cool_set_point,
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the activity.

        Returns:
            The activity dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the activity.

        Returns:
            The activity representation converted to a string.
        """
        return str(self.as_dict())


class ConfigZone:
    """Configurable schedule, hold, and activity settings for one zone."""

    def __init__(self, zone_json: dict[str, Any], vacation_json: dict[str, Any]) -> None:
        """Build zone configuration from Carrier zone and vacation settings.

        Args:
            zone_json: Raw enabled zone configuration from the Carrier API.
            vacation_json: Synthetic activity payload derived from system-level
                vacation set points and fan mode.
        """
        self.api_id = safely_get_json_value(zone_json, "id", str)
        self.name: str = safely_get_json_value(zone_json, "name")
        self.hold_activity: ActivityTypes = safely_get_json_value(
            zone_json, "holdActivity", ActivityTypes
        )
        self.hold: bool = safely_get_json_value(zone_json, "hold") == "on"
        self.hold_until: str = safely_get_json_value(zone_json, "otmr")
        self.program_json: dict = safely_get_json_value(zone_json, "program")
        self.occupancy_enabled: bool = safely_get_json_value(zone_json, "occEnabled") == "on"
        self.activities = []
        for zone_activity_json in safely_get_json_value(zone_json, "activities"):
            self.activities.append(ConfigZoneActivity(zone_activity_json=zone_activity_json))
        if vacation_json["fan"] is not None:
            self.activities.append(ConfigZoneActivity(zone_activity_json=vacation_json))

    def find_activity(self, activity_name: ActivityTypes) -> ConfigZoneActivity | None:
        """Find a configured zone activity by activity type.

        Args:
            activity_name: Activity type to locate.

        Returns:
            The matching configured activity, or ``None`` when the activity is
            not present for the zone.
        """
        for activity in self.activities:
            if activity.type == activity_name:
                return activity
        return None

    def yesterday_active_periods(self) -> list[dict[str, Any]]:
        """Return enabled schedule periods for yesterday.

        Returns:
            Enabled schedule periods from the zone's previous schedule day,
            using the local system date to select the day.
        """
        now = datetime.now(UTC).astimezone()
        sunday_0_index_today = int(now.date().strftime("%w"))
        yesterday_schedule = self.program_json["day"][(sunday_0_index_today + 8) % 7]
        return active_schedule_periods(yesterday_schedule["period"])

    def today_active_periods(self) -> list[dict[str, Any]]:
        """Return enabled schedule periods for today.

        Returns:
            Enabled schedule periods from the zone's current schedule day,
            using the local system date to select the day.
        """
        now = datetime.now(UTC).astimezone()
        sunday_0_index_today = int(now.date().strftime("%w"))
        today_schedule_json = self.program_json["day"][sunday_0_index_today]
        return active_schedule_periods(today_schedule_json["period"])

    def current_activity(self) -> ConfigZoneActivity | None:
        """Determine the zone activity that should currently be active.

        Held zones resolve directly to their hold activity. Scheduled zones use
        the latest enabled period earlier than the current local time, falling
        back to yesterday's final enabled period when today's schedule has not
        started yet.

        Returns:
            The configured current activity, or ``None`` when no active period is
            available in today or yesterday's schedule.
        """
        if self.hold:
            return self.find_activity(self.hold_activity)
        now = datetime.now(UTC).astimezone()
        reversed_active_periods = reversed(self.today_active_periods())
        for active_period in reversed_active_periods:
            hours, minutes = active_period["time"].split(":")
            if (int(hours) < now.hour) or (int(hours) == now.hour and int(minutes) < now.minute):
                return self.find_activity(
                    safely_get_json_value(active_period, "activity", ActivityTypes)
                )
        yesterday_active_periods = list(self.yesterday_active_periods())
        if not yesterday_active_periods:
            return None
        return self.find_activity(
            safely_get_json_value(yesterday_active_periods[-1], "activity", ActivityTypes)
        )

    def next_activity_time(self) -> str | None:
        """Find the next scheduled activity start time.

        Returns:
            The next enabled period time from today, the first enabled period
            from tomorrow, or ``None`` when neither day has enabled periods.
        """
        now = datetime.now(UTC).astimezone()
        sunday_0_index_today = int(now.date().strftime("%w"))
        active_periods = self.today_active_periods()
        for active_period in active_periods:
            hours, minutes = active_period["time"].split(":")
            if (int(hours) > now.hour) or (int(hours) == now.hour and int(minutes) > now.minute):
                return active_period["time"]
        tomorrow_schedule = self.program_json["day"][(sunday_0_index_today + 1) % 7]
        tomorrow_active_schedule_periods = active_schedule_periods(tomorrow_schedule["period"])
        if len(tomorrow_active_schedule_periods) > 0:
            return tomorrow_active_schedule_periods[0]["time"]
        return None

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the zone configuration.

        Returns:
            A dictionary containing hold state, occupancy configuration, current
            activity, and configured activities.
        """
        current_activity = self.current_activity()
        builder = {
            "api_id": self.api_id,
            "name": self.name,
            "current_activity": current_activity.as_dict() if current_activity else None,
            "hold_activity": self.hold_activity,
            "hold": self.hold,
            "hold_until": self.hold_until,
            "occupancy_enabled": self.occupancy_enabled,
            "activities": [activity.as_dict() for activity in self.activities],
        }
        if self.hold_activity is not None:
            builder["hold_activity"] = self.hold_activity.value
        return builder

    def __repr__(self) -> str:
        """Return a developer-readable representation of the zone configuration.

        Returns:
            The zone configuration dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the zone configuration.

        Returns:
            The zone configuration representation converted to a string.
        """
        return str(self.as_dict())


class Config:
    """Configurable system settings and enabled zone configurations."""

    temperature_unit: str | None = None
    mode: str | None = None
    heat_source: str | None = None
    etag: str | None = None
    fuel_type: str | None = None
    gas_unit: str | None = None
    zones: list[ConfigZone]
    uv_enabled: bool | None = None
    humidifier_enabled: bool | None = None
    humidifier_heat_target: int | None = None

    def __init__(
        self,
        raw: dict[str, Any],
    ) -> None:
        """Build system configuration from a Carrier GraphQL config payload.

        Args:
            raw: Raw ``config`` object returned by the Carrier GraphQL API.
        """
        self.raw = raw
        self.temperature_unit = safely_get_json_value(self.raw, "cfgem")
        self.mode = safely_get_json_value(self.raw, "mode")
        self.heat_source = safely_get_json_value(self.raw, "heatsource")
        self.etag = safely_get_json_value(self.raw, "etag")
        self.fuel_type = safely_get_json_value(self.raw, "fueltype")
        self.gas_unit = safely_get_json_value(self.raw, "gasunit")
        self.uv_enabled = safely_get_json_value(self.raw, "cfguv") == "on"
        self.humidifier_enabled = safely_get_json_value(self.raw, "cfghumid") == "on"
        self.humidifier_heat_target = safely_get_json_value(self.raw, "humidityHome.rhtg", int)
        if self.humidifier_heat_target is not None:
            self.humidifier_heat_target = self.humidifier_heat_target * 5
        vacation_json = {
            "type": "vacation",
            "clsp": self.raw["vacmaxt"],
            "htsp": self.raw["vacmint"],
            "fan": self.raw["vacfan"],
        }
        self.zones = []
        for zone_json in safely_get_json_value(self.raw, "zones"):
            if safely_get_json_value(zone_json, "enabled") == "on":
                self.zones.append(ConfigZone(zone_json=zone_json, vacation_json=vacation_json))

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the system configuration.

        Returns:
            A dictionary containing high-level settings and enabled zones.
        """
        return {
            "temperature_unit": self.temperature_unit,
            "mode": self.mode,
            "heat_source": self.heat_source,
            "zones": [zone.as_dict() for zone in self.zones or []],
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the configuration.

        Returns:
            The configuration dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the configuration.

        Returns:
            The configuration representation converted to a string.
        """
        return str(self.as_dict())
