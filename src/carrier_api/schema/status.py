from dataclasses import dataclass
from datetime import datetime, time
from logging import getLogger
from typing import Dict, Any, Optional, List
from marshmallow import Schema, EXCLUDE, fields, post_load, pre_load

from . import BaseSchema
from .boolean import BooleanWithSerialize
from .. import ActivityTypes, FanModes, SystemModes, TemperatureUnits

_LOGGER = getLogger(__name__)


@dataclass(kw_only=True)
class StatusZone:
    api_id: str
#    enabled: str
#    current_activity: ActivityTypes
    temperature: float
    humidity: int
    occupancy: Optional[bool] = None
#    fan: FanModes
    hold: bool
#    hold_until: Optional[time] = None
#    heat_set_point: float
#    cool_set_point: float
#    conditioning: str

    @property
    def zone_conditioning_system_mode(self) -> SystemModes:
        match self.conditioning:
            case "active_heat" | "prep_heat" | "pending_heat":
                return SystemModes.HEAT
            case "active_cool" | "prep_cool" | "pending_cool":
                return SystemModes.COOL
            case "idle":
                return SystemModes.OFF
        raise ValueError(f"Unknown conditioning: {self.conditioning}")


class StatusZoneSchema(BaseSchema):
    class Meta:
        unknown = EXCLUDE
    api_id = fields.String(data_key="id")
    enabled = fields.String(data_key="enabled", dump_default="on")
    current_activity = fields.Enum(ActivityTypes, by_value=True, data_key="currentActivity")
    temperature = fields.Float(data_key="rt")
    humidity = fields.Integer(data_key="rh")
    occupancy = BooleanWithSerialize(truthy=["occupied"], falsy=["unoccupied"])
    fan = fields.Enum(FanModes, by_value=True)
    hold = BooleanWithSerialize(truthy=["on"], falsy=["off"])
    hold_until = fields.Time(data_key="otmr")
    heat_set_point = fields.Float(data_key="htsp")
    cool_set_point = fields.Float(data_key="clsp")
    conditioning = fields.String(data_key="zoneconditioning")

    @post_load
    def make(self, data, **kwargs):
        return StatusZone(**data)


@dataclass(kw_only=True)
class InDoorUnit:
    airflow_cfm: int
    blower_rpm: int
    static_pressure: float
    operational_status: str
    type: str


class InDoorUnitSchema(BaseSchema):
    class Meta:
        unknown = EXCLUDE
    airflow_cfm = fields.Integer(data_key="cfm")
    blower_rpm = fields.Integer(data_key="blwrpm")
    static_pressure = fields.Float(data_key="statpress")
    operational_status = fields.String(data_key="opstat")
    type = fields.String()

    @post_load
    def make(self, data, **kwargs):
        return InDoorUnit(**data)


@dataclass(kw_only=True)
class OutDoorUnit:
    operational_status: str
    type: str


class OutDoorUnitSchema(BaseSchema):
    class Meta:
        unknown = EXCLUDE
    operational_status = fields.String(data_key="opstat")
    type = fields.String()

    @post_load
    def make(self, data, **kwargs):
        return OutDoorUnit(**data)


@dataclass(kw_only=True)
class Status:
    outdoor_temperature: float
    mode: str
    temperature_unit: TemperatureUnits
    filter_used: int
    humidity_level: int
    humidifier_on: bool
    uv_lamp_level: int
    is_disconnected: bool
    indoor_unit: InDoorUnit
    outdoor_unit: OutDoorUnit
    time_stamp: datetime
    zones: List[StatusZone]


class StatusSchema(BaseSchema):
    class Meta:
        unknown = EXCLUDE
    outdoor_temperature = fields.Float(data_key="oat")
    mode = fields.String()
    temperature_unit = fields.Enum(TemperatureUnits, by_value=True, data_key="cfgem")
    filter_used = fields.Integer(data_key="filtrlvl")
    humidity_level = fields.Integer(data_key="humlvl")
    humidifier_on = BooleanWithSerialize(truthy=["on"], falsy=["off"], data_key="humid")
    uv_lamp_level = fields.Integer(data_key="uvlvl")
    is_disconnected = fields.Boolean(data_key="isDisconnected")
    indoor_unit = fields.Nested(InDoorUnitSchema, data_key="idu")
    outdoor_unit = fields.Nested(OutDoorUnitSchema, data_key="odu")
    time_stamp = fields.DateTime(data_key="utcTime")
    zones = fields.List(fields.Nested(StatusZoneSchema))

    @pre_load
    def skip_zones(self, data, **kwargs):
        enabled_zones = []
        for zone in data.get("zones", []):
            if zone["enabled"] == "on":
                enabled_zones.append(zone)
        data["zones"] = enabled_zones
        return data

    @post_load
    def make(self, data, **kwargs):
        return Status(**data)
