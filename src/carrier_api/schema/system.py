from dataclasses import dataclass
from typing import Optional

from . import _BaseModel
from .. import Profile, Status, Config, InfinityEnergy


@dataclass(kw_only=True)
class System(_BaseModel):
    profile: Profile
    status: Status
    config: Config
    energy: Optional[InfinityEnergy]
