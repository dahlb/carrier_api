import logging

from dateutil.parser import isoparse
import datetime

from .const import SystemModes, TemperatureUnits, FanModes, ActivityNames
from .util import safely_get_json_value

_LOGGER = logging.getLogger(__name__)


class StatusZone:
    def __init__(self, status_zone_json: dict):
        self.api_id = safely_get_json_value(status_zone_json, "$.id")
        self.name: str = safely_get_json_value(status_zone_json, "name")
        self.current_activity: ActivityNames = ActivityNames(status_zone_json["currentActivity"])
        self.temperature: float = safely_get_json_value(status_zone_json, "rt", float)
        self.humidity: int = safely_get_json_value(status_zone_json, "rh", int)
        self.occupancy: bool = safely_get_json_value(status_zone_json, "occupancy") == "occupied"
        self.fan: FanModes = FanModes(status_zone_json["fan"])
        self.hold: bool = safely_get_json_value(status_zone_json, "hold") == "on"
        self.hold_until: str = safely_get_json_value(status_zone_json, "otmr")
        self.heat_set_point: float = safely_get_json_value(status_zone_json, "htsp", float)
        self.cool_set_point: float = safely_get_json_value(status_zone_json, "clsp", float)
        self.conditioning: str = safely_get_json_value(status_zone_json, "zoneconditioning")

    @property
    def zone_conditioning_const(self) -> str:
        match self.conditioning:
            case "active_heat" | "prep_heat" | "pending_heat":
                return SystemModes.HEAT
            case "active_cool" | "prep_cool" | "pending_cool":
                return SystemModes.COOL
            case "idle":
                return SystemModes.OFF

    def __repr__(self):
        return {
            "id": self.api_id,
            "name": self.name,
            "current_activity": self.current_activity.value,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "fan": self.fan.value,
            "hold": self.hold,
            "occupancy": self.occupancy,
            "hold_until": self.hold_until,
            "heat_set_point": self.heat_set_point,
            "cool_set_point": self.cool_set_point,
            "conditioning": self.conditioning,
        }

    def __str__(self):
        return str(self.__repr__())


class Status:
    outdoor_temperature: int = None
    mode: str = None
    temperature_unit: str = None
    filter_used: int = None
    is_disconnected: bool = None
    airflow_cfm: int = None
    time_stamp: datetime = None
    zones: [StatusZone] = None
    raw_status_json: dict = None

    def __init__(
        self,
        system,
    ):
        self.system = system
        self.refresh()

    def refresh(self):
        self.raw_status_json = self.system.api_connection.get_status(
            system_serial=self.system.serial
        )
        self.outdoor_temperature: float = safely_get_json_value(self.raw_status_json, "oat", float)
        self.mode: str = self.raw_status_json["mode"]
        self.temperature_unit: TemperatureUnits = TemperatureUnits(self.raw_status_json["cfgem"])
        self.filter_used: int = safely_get_json_value(self.raw_status_json, "filtrlvl", int)
        self.is_disconnected: bool = safely_get_json_value(self.raw_status_json, "isDisconnected", bool)
        self.airflow_cfm: int = safely_get_json_value(self.raw_status_json, "idu.cfm", int)
        self.time_stamp = isoparse(safely_get_json_value(self.raw_status_json, "timestamp"))
        self.zones = []
        for zone_json in self.raw_status_json["zones"]["zone"]:
            if safely_get_json_value(zone_json, "enabled") == "on":
                self.zones.append(StatusZone(zone_json))

    @property
    def mode_const(self) -> str:
        match self.mode:
            case "gasheat" | "electric" | "hpheat":
                return SystemModes.HEAT
            case "dehumidify":
                return SystemModes.COOL

    def __repr__(self):
        return {
            "outdoor_temperature": self.outdoor_temperature,
            "mode": self.mode,
            "temperature_unit": self.temperature_unit.value,
            "filter_used": self.filter_used,
            "is_disconnected": self.is_disconnected,
            "airflow_cfm": self.airflow_cfm,
            "time_stamp": self.time_stamp.astimezone().strftime("%m/%d/%Y, %H:%M:%S %Z"),
            "zones": list(map(lambda zone: zone.__repr__(), self.zones)),
        }

    def __str__(self):
        return str(self.__repr__())
