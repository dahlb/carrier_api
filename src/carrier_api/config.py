import logging
from datetime import datetime
from dateutil.parser import isoparse

from .const import FanModes, ActivityNames
from .util import safely_get_json_value

_LOGGER = logging.getLogger(__name__)


def active_schedule_periods(periods_json: [dict]):
    return list(filter(lambda period: safely_get_json_value(period, "enabled") == "on", periods_json))


class ConfigZoneActivity:
    def __init__(self, zone_activity_json: dict):
        self.api_id: ActivityNames = ActivityNames(safely_get_json_value(zone_activity_json, "$.id"))
        self.fan: FanModes = FanModes(zone_activity_json["fan"])
        self.heat_set_point: float = safely_get_json_value(zone_activity_json, "htsp", float)
        self.cool_set_point: float = safely_get_json_value(zone_activity_json, "clsp", float)

    def __repr__(self):
        return {
            "api_id": self.api_id.value,
            "fan": self.fan.value,
            "heat_set_point": self.heat_set_point,
            "cool_set_point": self.cool_set_point,
        }

    def __str__(self):
        return str(self.__repr__())


class ConfigZone:
    def __init__(self, zone_json: dict, vacation_json: dict):
        self.api_id = safely_get_json_value(zone_json, "$.id")
        self.name: str = safely_get_json_value(zone_json, "name")
        self.hold_activity: ActivityNames = safely_get_json_value(zone_json, "holdActivity", ActivityNames)
        self.hold: bool = safely_get_json_value(zone_json, "hold") == "on"
        self.hold_until: str = safely_get_json_value(zone_json, "otmr")
        self.program_json: dict = safely_get_json_value(zone_json, "program")
        self.activities = []
        for zone_activity_json in safely_get_json_value(zone_json, "activities.activity"):
            self.activities.append(
                ConfigZoneActivity(zone_activity_json=zone_activity_json)
            )
        self.activities.append(ConfigZoneActivity(zone_activity_json=vacation_json))

    def find_activity(self, activity_name: ActivityNames):
        for activity in self.activities:
            if activity.api_id == activity_name:
                return activity

    def yesterday_active_periods(self):
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        yesterday_schedule = self.program_json["day"][(sunday_0_index_today + 8) % 7]
        return active_schedule_periods(yesterday_schedule["period"])

    def today_active_periods(self):
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        today_schedule_json = self.program_json["day"][sunday_0_index_today]
        return active_schedule_periods(today_schedule_json["period"])

    def current_activity(self) -> ConfigZoneActivity:
        if self.hold:
            return self.find_activity(self.hold_activity)
        else:
            now = datetime.now()
            reversed_active_periods = reversed(self.today_active_periods())
            for active_period in reversed_active_periods:
                hours, minutes = active_period["time"].split(":")
                if (int(hours) < now.hour) or (
                    int(hours) == now.hour and int(minutes) < now.minute
                ):
                    return self.find_activity(safely_get_json_value(active_period, "activity", ActivityNames))
            yesterday_active_periods = list(self.yesterday_active_periods())
            return self.find_activity(safely_get_json_value(yesterday_active_periods[-1], "activity", ActivityNames))

    def next_activity_time(self) -> str | None:
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        active_periods = self.today_active_periods()
        for active_period in active_periods:
            hours, minutes = active_period["time"].split(":")
            if (int(hours) > now.hour) or (
                int(hours) == now.hour and int(minutes) > now.minute
            ):
                return active_period["time"]
        tomorrow_schedule = self.program_json["day"][(sunday_0_index_today + 1) % 7]
        tomorrow_active_schedule_periods = active_schedule_periods(tomorrow_schedule["period"])
        if len(tomorrow_active_schedule_periods) > 0:
            return tomorrow_active_schedule_periods[0]["time"]
        else:
            return None

    def __repr__(self):
        builder = {
            "api_id": self.api_id,
            "name": self.name,
            "current_activity": self.current_activity().__repr__(),
            "hold_activity": self.hold_activity,
            "hold": self.hold,
            "hold_until": self.hold_until,
            "activities": [activity.__repr__() for activity in self.activities],
        }
        if self.hold_activity is not None:
            builder["hold_activity"] = self.hold_activity.value
        return builder

    def __str__(self):
        return str(self.__repr__())


class Config:
    temperature_unit: str = None
    static_pressure: float = None
    mode: str = None
    heat_source: str = None
    limit_min: int = None
    limit_max: int = None
    time_stamp: datetime = None
    zones: [ConfigZone] = None
    raw_config_json: dict = None

    def __init__(
        self,
        system,
    ):
        self.system = system
        self.refresh()

    def refresh(self):
        self.raw_config_json = self.system.api_connection.get_config(
            system_serial=self.system.serial
        )
        _LOGGER.debug(f"raw_config_json:{self.raw_config_json}")
        self.temperature_unit = safely_get_json_value(self.raw_config_json, "cfgem")
        self.static_pressure = safely_get_json_value(self.raw_config_json, "staticPressure")
        self.mode = safely_get_json_value(self.raw_config_json, "mode")
        self.heat_source = safely_get_json_value(self.raw_config_json, "heatsource")
        self.limit_min = safely_get_json_value(self.raw_config_json, "utilityEvent.minLimit", int)
        self.limit_max = safely_get_json_value(self.raw_config_json, "utilityEvent.maxLimit", int)
        self.time_stamp = isoparse(safely_get_json_value(self.raw_config_json, "timestamp"))
        vacation_json = {
            "$": {"id": "vacation"},
            "clsp": self.raw_config_json["vacmaxt"],
            "htsp": self.raw_config_json["vacmint"],
            "fan": self.raw_config_json["vacfan"],
        }
        self.zones = []
        for zone_json in safely_get_json_value(self.raw_config_json, "zones.zone"):
            if safely_get_json_value(zone_json, "enabled") == "on":
                self.zones.append(
                    ConfigZone(zone_json=zone_json, vacation_json=vacation_json)
                )

    def __repr__(self):
        return {
            "temperature_unit": self.temperature_unit,
            "static_pressure": self.static_pressure,
            "mode": self.mode,
            "heat_source": self.heat_source,
            "limit_min": self.limit_min,
            "limit_max": self.limit_max,
            "zones": [zone.__repr__() for zone in self.zones],
        }

    def __str__(self):
        return str(self.__repr__())
