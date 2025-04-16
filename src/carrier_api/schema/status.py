from dataclasses import dataclass
from datetime import datetime, time
from logging import getLogger
from typing import Annotated, Dict, Any, Optional, List

from mashumaro.types import Alias

from . import _BaseModel
from .. import ActivityTypes, FanModes, SystemModes, TemperatureUnits

_LOGGER = getLogger(__name__)


@dataclass(kw_only=True)
class StatusZone(_BaseModel):
    api_id: Annotated[str, Alias("id")]
    _enabled: Annotated[str, Alias("enabled")] = "on"
    current_activity: Annotated[ActivityTypes, Alias("currentActivity")]
    temperature: Annotated[float, Alias("rt")]
    humidity: Annotated[int, Alias("rh")]
    occupancy: Optional[bool] | None
    fan: Annotated[FanModes, Alias("fan")]
    hold: bool
    hold_until: Annotated[Optional[time], Alias("otmr")]
    heat_set_point: Annotated[float, Alias("htsp")]
    cool_set_point: Annotated[float, Alias("clsp")]
    conditioning: Annotated[str, Alias("zoneconditioning")]

    @classmethod
    def __pre_deserialize__(cls, d: Dict[Any, Any]) -> Dict[Any, Any]:
        d["occupancy"] = d.get("occupancy", None) == "occupied"
        d["hold"] = d["hold"] == "on"
        return d

    def __post_serialize__(self, d: Dict, context: Optional[Dict] = None):
        if d["occupancy"]:
            d["occupancy"] = "occupied"
        else:
            d["occupancy"] = "unoccupied"
        if d["hold"]:
            d["hold"] = "on"
        else:
            d["hold"] = "off"
        return d

    @property
    def zone_conditioning_const(self) -> SystemModes:
        match self.conditioning:
            case "active_heat" | "prep_heat" | "pending_heat":
                return SystemModes.HEAT
            case "active_cool" | "prep_cool" | "pending_cool":
                return SystemModes.COOL
            case "idle":
                return SystemModes.OFF
        raise ValueError(f"Unknown conditioning: {self.conditioning}")


@dataclass(kw_only=True)
class InDoorUnit(_BaseModel):
    airflow_cfm: Annotated[int, Alias("cfm")]
    blower_rpm: Annotated[int, Alias("blwrpm")]
    static_pressure: Annotated[float, Alias("statpress")]
    operational_status: Annotated[str, Alias("opstat")]
    type: Annotated[str, Alias("type")]


@dataclass(kw_only=True)
class OutDoorUnit(_BaseModel):
    operational_status: Annotated[str, Alias("opstat")]
    type: Annotated[str, Alias("type")]


@dataclass(kw_only=True)
class Status(_BaseModel):
    outdoor_temperature: Annotated[float, Alias("oat")]
    mode: str
    temperature_unit: Annotated[TemperatureUnits, Alias("cfgem")]
    filter_used: Annotated[int, Alias("filtrlvl")]
    humidity_level: Annotated[int, Alias("humlvl")]
    humidifier_on: Annotated[bool, Alias("humid")]
    uv_lamp_level: Annotated[int, Alias("uvlvl")]
    is_disconnected: Annotated[bool, Alias("isDisconnected")]
    indoor_unit: Annotated[InDoorUnit, Alias("idu")]
    outdoor_unit: Annotated[OutDoorUnit, Alias("odu")]
    time_stamp: Annotated[datetime, Alias("utcTime")]
    zones: List[StatusZone]

    @classmethod
    def __pre_deserialize__(cls, d: Dict[Any, Any]) -> Dict[Any, Any]:
        enabled_zones = []
        for zone in d.get("zones", []):
            if zone["enabled"] == "on":
                enabled_zones.append(zone)
        d["zones"] = enabled_zones
        d["humid"] = d["humid"] == "on"
        return d

    def __post_serialize__(self, d: Dict, context: Optional[Dict] = None):
        if d["humid"]:
            d["humid"] = "on"
        else:
            d["humid"] = "off"
        return d
