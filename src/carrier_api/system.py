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
            "profile": self.profile.__repr__(),
            "status": self.status.__repr__(),
            "config": self.config.__repr__(),
        }

    def __str__(self):
        return str(self.__repr__())
