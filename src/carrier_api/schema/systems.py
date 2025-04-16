from dataclasses import dataclass
from typing import List, Annotated

from mashumaro.types import Alias

from . import _BaseModel
from .system import System


@dataclass(kw_only=True)
class Systems(_BaseModel):
    systems: Annotated[List[System], Alias("infinitySystems")]
