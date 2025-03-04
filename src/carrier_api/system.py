from logging import getLogger

from .profile import Profile
from .status import Status
from .energy import Energy
from .config import Config


_LOGGER = getLogger(__name__)


class System:
    def __init__(
            self,
            profile: Profile,
            status: Status,
            config: Config,
            energy: Energy,
    ):
        self.profile = profile
        self.status = status
        self.energy = energy
        self.config = config

    def __repr__(self):
        return {
            "serial": self.profile.serial,
            "name": self.profile.name,
            "profile": self.profile.__repr__(),
            "status": self.status.__repr__(),
            "config": self.config.__repr__(),
            "energy": self.energy.__repr__(),
        }

    def __str__(self):
        return str(self.__repr__())
