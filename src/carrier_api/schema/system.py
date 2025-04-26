from dataclasses import dataclass
from typing import Optional

from . import _BaseModel
from .. import Profile, Status, Config, InfinityEnergy


@dataclass(kw_only=True)
class System(_BaseModel):
    profile: Profile = None
    status: Status = None
    config: Config = None
    energy: Optional[InfinityEnergy] = None
