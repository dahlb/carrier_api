import logging
from datetime import datetime

from .const import FanModes, ActivityNames

_LOGGER = logging.getLogger(__name__)


def active_schedule_periods(periods_json: [dict]):
    return list(filter(lambda period: period["enabled"] == "on", periods_json))


class ConfigZoneActivity:
    def __init__(self, zone_activity_json: dict):
        self.api_id: ActivityNames = ActivityNames(zone_activity_json["$"]["id"])
        self.fan: FanModes = FanModes(zone_activity_json["fan"])
        self.heat_set_point: float = float(zone_activity_json["htsp"])
        self.cool_set_point: float = float(zone_activity_json["clsp"])

    def __repr__(self):
        return {
            "api_id": self.api_id.value,
            "fan": self.fan.value,
            "heat_set_point": self.heat_set_point,
            "cool_set_point": self.cool_set_point,
        }

    def __str__(self):
        return f"{self.__repr__()}"


class ConfigZone:
    def __init__(self, zone_json: dict, vacation_json: dict):
        self.api_id = zone_json["$"]["id"]
        self.name: str = zone_json["name"]
        raw_hold_activity_name = zone_json.get("holdActivity", None)
        self.hold_activity: ActivityNames = None
        if raw_hold_activity_name is not None:
            self.hold_activity: ActivityNames = ActivityNames(raw_hold_activity_name)
        self.hold: bool = zone_json["hold"] == "on"
        self.hold_until: str = zone_json.get("otmr", None)
        self.program_json: dict = zone_json["program"]
        self.activities = []
        for zone_activity_json in zone_json["activities"]["activity"]:
            self.activities.append(
                ConfigZoneActivity(zone_activity_json=zone_activity_json)
            )
        self.activities.append(ConfigZoneActivity(zone_activity_json=vacation_json))

    def find_activity(self, activity_name: ActivityNames):
        for activity in self.activities:
            if activity.api_id == activity_name:
                return activity

    def current_activity(self) -> ConfigZoneActivity:
        if self.hold:
            return self.find_activity(self.hold_activity)
        else:
            now = datetime.now()
            sunday_0_index_today = int(now.date().strftime("%w"))
            today_schedule_json = self.program_json["day"][sunday_0_index_today]
            active_periods = reversed(
                active_schedule_periods(today_schedule_json["period"])
            )
            for active_period in active_periods:
                hours, minutes = active_period["time"].split(":")
                if (int(hours) < now.hour) or (
                    int(hours) == now.hour and int(minutes) < now.minute
                ):
                    return self.find_activity(ActivityNames(active_period["activity"]))
            yesterday_schedule = self.program_json["day"][sunday_0_index_today + 8 % 7]
            yesterday_active_periods = reversed(
                active_schedule_periods(yesterday_schedule["period"])
            )
            return self.find_activity(ActivityNames(yesterday_active_periods[-1]["activity"]))

    def next_activity_time(self) -> str:
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        today_schedule_json = self.program_json["day"][sunday_0_index_today]
        active_periods = active_schedule_periods(today_schedule_json["period"])
        for active_period in active_periods:
            hours, minutes = active_period["time"].split(":")
            if (int(hours) > now.hour) or (
                int(hours) == now.hour and int(minutes) > now.minute
            ):
                return active_period["time"]
        tomorrow_schedule = self.program_json["day"][sunday_0_index_today + 1 % 7]
        return active_schedule_periods(tomorrow_schedule["period"])[0]["time"]

    def __repr__(self):
        builder = {
            "api_id": self.api_id.value,
            "name": self.name,
            "hold_activity": self.hold_activity,
            "hold": self.hold,
            "hold_until": self.hold_until,
            "activities": list(map(lambda activity: activity.__repr__(), self.activities)),
        }
        if self.hold_activity is not None:
            builder["hold_activity"] = self.hold_activity.value
        return builder

    def __str__(self):
        builder = self.__repr__()
        builder["activities"] = ", ".join(
            map(lambda activity: activity.__str__(), self.activities)
        )
        return str(builder)


class Config:
    temperature_unit: str = None
    static_pressure: float = None
    mode: str = None
    limit_min: int = None
    limit_max: int = None
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
        self.temperature_unit = self.raw_config_json["cfgem"]
        self.static_pressure = self.raw_config_json["staticPressure"]
        self.mode = self.raw_config_json["mode"]
        self.limit_min = int(self.raw_config_json["utilityEvent"]["minLimit"])
        self.limit_max = int(self.raw_config_json["utilityEvent"]["maxLimit"])
        vacation_json = {
            "$": {"id": "vacation"},
            "clsp": self.raw_config_json["vacmaxt"],
            "htsp": self.raw_config_json["vacmint"],
            "fan": self.raw_config_json["vacfan"],
        }
        self.zones = []
        for zone_json in self.raw_config_json["zones"]["zone"]:
            if zone_json["enabled"] == "on":
                self.zones.append(
                    ConfigZone(zone_json=zone_json, vacation_json=vacation_json)
                )

    def __repr__(self):
        return {
            "temperature_unit": self.temperature_unit,
            "static_pressure": self.static_pressure,
            "mode": self.mode,
            "limit_min": self.limit_min,
            "limit_max": self.limit_max,
            "zones": list(map(lambda zone: zone.__repr__(), self.zones)),
        }

    def __str__(self):
        builder = self.__repr__()
        builder["zones"] = ", ".join(map(lambda zone: zone.__str__(), self.zones))
        return str(builder)
