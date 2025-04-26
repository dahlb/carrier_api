from dataclasses import dataclass
from datetime import datetime, time
from logging import getLogger
from typing import Annotated, Dict, Any, Optional, List

from mashumaro.types import Alias

from . import _BaseModel
from .. import ActivityTypes, FanModes, TemperatureUnits

_LOGGER = getLogger(__name__)


@dataclass(kw_only=True)
class ConfigZoneActivity(_BaseModel):
    type: ActivityTypes
    api_id: Annotated[str, Alias("id")]
    fan: FanModes
    heat_set_point: Annotated[float, Alias("htsp")]
    cool_set_point: Annotated[float, Alias("clsp")]


@dataclass(kw_only=True)
class ConfigZoneProgramDayPeriod(_BaseModel):
    api_id: Annotated[str, Alias("id")]
    zone_id: Annotated[str, Alias("zoneId")]
    day_id: Annotated[str, Alias("dayId")]
    activity: Annotated[ActivityTypes, Alias("activity")]
    time: Annotated[time, Alias("time")]
    _enabled: Annotated[str, Alias("enabled")] = "on"


@dataclass(kw_only=True)
class ConfigZoneProgramDay(_BaseModel):
    api_id: Annotated[str, Alias("id")]
    zone_id: Annotated[str, Alias("zoneId")]
    periods: Annotated[List[ConfigZoneProgramDayPeriod], Alias("period")]

    @classmethod
    def __pre_deserialize__(cls, d: Dict[Any, Any]) -> Dict[Any, Any]:
        enabled_periods = []
        for period in d.get("period", []):
            if period["enabled"] == "on":
                enabled_periods.append(period)
        d["period"] = enabled_periods
        return d


@dataclass(kw_only=True)
class ConfigZoneProgram(_BaseModel):
    api_id: Annotated[str, Alias("id")]
    days: Annotated[List[ConfigZoneProgramDay], Alias("day")]


@dataclass(kw_only=True)
class ConfigZone(_BaseModel):
    api_id: Annotated[str, Alias("id")]
    name: str
    _enabled: Annotated[str, Alias("enabled")] = "on"
    hold_activity: Annotated[Optional[ActivityTypes], Alias("holdActivity")] = None
    hold: Annotated[bool, Alias("hold")]
    hold_until: Annotated[Optional[str], Alias("otmr")] = None
    program: ConfigZoneProgram
    occupancy_enabled: Annotated[bool, Alias("occEnabled")]
    activities: List[ConfigZoneActivity]

    @classmethod
    def __pre_deserialize__(cls, d: Dict[Any, Any]) -> Dict[Any, Any]:
        d["hold"] = d["hold"] == "on"
        d["occEnabled"] = d.get("occEnabled", None) == "on"
        if d.get("otmr", None) == "None":
            d["otmr"] = None
        if d["holdActivity"] == "None":
            d["holdActivity"] = None
        return d

    def __post_serialize__(self, d: Dict, context: Optional[Dict] = None):
        if d["hold"]:
            d["hold"] = "on"
        else:
            d["hold"] = "off"
        if d["occEnabled"]:
            d["occEnabled"] = "on"
        else:
            d["occEnabled"] = "off"
        return d

    def find_activity(self, activity_name: ActivityTypes) -> Optional[ConfigZoneActivity]:
        for activity in self.activities:
            if activity.type == activity_name:
                return activity

    def yesterday_active_periods(self) -> List[ConfigZoneProgramDayPeriod]:
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        yesterday_schedule = self.program.days[(sunday_0_index_today + 8) % 7]
        return yesterday_schedule.periods

    def today_active_periods(self) -> List[ConfigZoneProgramDayPeriod]:
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        today_schedule = self.program.days[sunday_0_index_today]
        return today_schedule.periods

    def current_activity(self) -> ConfigZoneActivity:
        if self.hold:
            return self.find_activity(self.hold_activity)
        else:
            now = datetime.now()
            reversed_active_periods = reversed(self.today_active_periods())
            for active_period in reversed_active_periods:
                hours = active_period.time.hour
                minutes = active_period.time.minute
                if (int(hours) < now.hour) or (
                    int(hours) == now.hour and int(minutes) < now.minute
                ):
                    return self.find_activity(active_period.activity)
            yesterday_active_periods = list(self.yesterday_active_periods())
            return self.find_activity(yesterday_active_periods[-1].activity)

    def next_activity_time(self) -> time | None:
        now = datetime.now()
        sunday_0_index_today = int(now.date().strftime("%w"))
        active_periods = self.today_active_periods()
        for active_period in active_periods:
            hours = active_period.time.hour
            minutes = active_period.time.minute
            if (int(hours) > now.hour) or (
                int(hours) == now.hour and int(minutes) > now.minute
            ):
                return active_period.time
        tomorrow_schedule = self.program.days[(sunday_0_index_today + 1) % 7]
        tomorrow_active_schedule_periods = tomorrow_schedule.periods
        if len(tomorrow_active_schedule_periods) > 0:
            return tomorrow_active_schedule_periods[0].time
        else:
            return None


@dataclass(kw_only=True)
class Config(_BaseModel):
    temperature_unit: Annotated[TemperatureUnits, Alias("cfgem")]
    mode: str
    heat_source: Annotated[str, Alias("heatsource")]
    etag: str
    fuel_type: Annotated[str, Alias("fueltype")]
    gas_unit: Annotated[str, Alias("gasunit")]
    uv_enabled: Annotated[bool, Alias("cfguv")]
    humidifier_enabled: Annotated[bool, Alias("cfghumid")]
    vacation_cool_set_point: Annotated[float, Alias("vacmaxt")]
    vacation_heat_set_point: Annotated[float, Alias("vacmint")]
    vacation_fan: Annotated[Optional[FanModes], Alias("vacfan")] = None
    zones: List[ConfigZone]

    @classmethod
    def __pre_deserialize__(cls, d: Dict[Any, Any]) -> Dict[Any, Any]:
        enabled_zones = []
        for zone in d.get("zones", []):
            if zone["enabled"] == "on":
                enabled_zones.append(zone)
        d["zones"] = enabled_zones
        d["cfguv"] = d["cfguv"] == "on"
        d["cfghumid"] = d["cfghumid"] == "on"
        if d["vacfan"] == "None":
            d["vacfan"] = None
        return d

    def __post_serialize__(self, d: Dict, context: Optional[Dict] = None):
        if d["cfguv"]:
            d["cfguv"] = "on"
        else:
            d["cfguv"] = "off"
        if d["cfghumid"]:
            d["cfghumid"] = "on"
        else:
            d["cfghumid"] = "off"
        return d
