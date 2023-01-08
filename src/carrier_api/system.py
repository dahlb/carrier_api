import logging

from .profile import Profile
from .status import Status
from .config import Config


_LOGGER = logging.getLogger(__name__)


class System:
    def __init__(
        self,
        api_connection,
        serial: str,
        name: str,
    ):
        self.api_connection = api_connection
        self.serial = serial
        self.name = name
        self.profile = Profile(system=self)
        self.status = Status(system=self)
        self.config = Config(system=self)

    def __repr__(self):
        return {
            "serial": self.serial,
            "name": self.name,
            "profile": str(self.profile),
            "status": str(self.status),
            "config": str(self.config),
        }

    def __str__(self):
        return f"{self.__repr__()}"
