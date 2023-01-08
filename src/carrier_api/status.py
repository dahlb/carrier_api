import logging

from .const import MODE_HEAT, MODE_COOL, MODE_OFF, SystemModes

_LOGGER = logging.getLogger(__name__)


class StatusZone:
    def __init__(
        self,
        status_zone_json: dict
    ):
        self.api_id = status_zone_json["$"]["id"]
        self.name = status_zone_json["name"]
        self.current_activity = status_zone_json["currentActivity"]
        self.temperature = status_zone_json["rt"]
        self.humidity = status_zone_json["rh"]
        self.fan = status_zone_json["fan"]
        self.hold = status_zone_json["hold"] == "on"
        self.hold_until = status_zone_json.get("otmr", None)
        self.heat_set_point = status_zone_json["htsp"]
        self.cool_set_point = status_zone_json["clsp"]
        self.conditioning = status_zone_json["zoneconditioning"]

    @property
    def zone_conditioning_const(self) -> str:
        match self.conditioning:
            case 'active_heat' | 'prep_heat' | 'pending_heat':
                return MODE_HEAT
            case 'active_cool' | 'prep_cool' | 'pending_cool':
                return MODE_COOL
            case 'idle':
                return MODE_OFF

    def __repr__(self):
        return {
            "id": self.api_id,
            "name": self.name,
            "current_activity": self.current_activity,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "fan": self.fan,
            "hold": self.hold,
            "hold_until": self.hold_until,
            "heat_set_point": self.heat_set_point,
            "cool_set_point": self.cool_set_point,
            "conditioning": self.conditioning,
        }

    def __str__(self):
        return f"{self.__repr__()}"


class Status:
    outdoor_temperature:int = None
    mode: str = None
    temperature_unit: str = None
    filter_used: int = None
    is_disconnected: bool = None
    zones: [StatusZone] = None
    raw_status_json: dict = None

    def __init__(
        self,
        system,
    ):
        self.system = system
        self.refresh()

    def refresh(self):
        self.raw_status_json = self.system.api_connection.get_status(system_serial=self.system.serial)
        self.outdoor_temperature = int(self.raw_status_json["oat"])
        self.mode = self.raw_status_json["mode"]
        self.temperature_unit = self.raw_status_json["cfgem"]
        self.filter_used = self.raw_status_json["filtrlvl"]
        self.is_disconnected = self.raw_status_json["isDisconnected"]
        self.zones = []
        for zone_json in self.raw_status_json["zones"]["zone"]:
            if zone_json["enabled"] == "on":
                self.zones.append(StatusZone(zone_json))

    @property
    def mode_const(self) -> str:
        match self.mode:
            case 'gasheat' | 'electric' | 'hpheat':
                return SystemModes.HEAT
            case 'dehumidify':
                return SystemModes.COOL

    def __repr__(self):
        return {
            "outdoor_temperature": self.outdoor_temperature,
            "mode": self.mode,
            "temperature_unit": self.temperature_unit,
            "filter_used": self.filter_used,
            "is_disconnected": self.is_disconnected,
            "zones": ",".join(map(str, self.zones)),
        }

    def __str__(self):
        return f"{self.__repr__()}"

