"""Schema for Blueair AWS (abs)."""
from dataclasses import dataclass
from datetime import time
from typing import Annotated, Optional, Dict, Any, Union

from mashumaro.config import BaseConfig
from mashumaro.mixins.dict import DataClassDictMixin
from mashumaro.types import Alias


class _BaseModel(DataClassDictMixin):
    """Model shared between schema definitions."""

    class Config(BaseConfig):
        """Base configuration."""

        forbid_extra_keys = False
        serialize_by_alias = True
        debug = True

@dataclass(kw_only=True)
class StatusZone(_BaseModel):
    api_id: Annotated[str, Alias("id")]
    _enabled: Annotated[str, Alias("enabled")] = "on"
    temperature: Annotated[float, Alias("rt")]
    humidity: Annotated[int, Alias("rh")]
    occupancy: Optional[bool]
    hold: bool
    hold_until: Annotated[Union[time, None], Alias("otmr")]
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


StatusZone.from_dict({
                  "id":"1",
                  "rt":"74",
                  "rh":"32",
                  "fan":"med",
                  "htsp":"74",
                  "clsp":"78",
                  "hold":"off",
                  "enabled":"on",
                  "currentActivity":"wake",
                  "zoneconditioning":"active_heat"
               })