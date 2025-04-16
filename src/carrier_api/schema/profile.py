from dataclasses import dataclass
from typing import Annotated

from mashumaro.types import Alias

from . import _BaseModel


@dataclass(kw_only=True)
class Profile(_BaseModel):
    name: str
    serial: str
    model: str
    brand: str
    firmware: str
    indoor_model: Annotated[str, Alias("indoorModel")]
    indoor_serial: Annotated[str, Alias("indoorSerial")]
    indoor_unit_type: Annotated[str, Alias("idutype")]
    indoor_unit_source: Annotated[str, Alias("idusource")]
    outdoor_model: Annotated[str, Alias("outdoorModel")]
    outdoor_serial: Annotated[str, Alias("outdoorSerial")]
    outdoor_unit_type: Annotated[str, Alias("odutype")]
