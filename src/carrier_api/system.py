"""Aggregate model for a Carrier system and its related state."""

from logging import getLogger

from .profile import Profile
from .status import Status
from .energy import Energy
from .config import Config


_LOGGER = getLogger(__name__)


class System:
    """Carrier system composed from profile, status, config, and energy data."""

    def __init__(
        self,
        profile: Profile,
        status: Status,
        config: Config,
        energy: Energy,
    ) -> None:
        """Create a Carrier system aggregate.

        Args:
            profile: Static system identity and equipment metadata.
            status: Current operational state for the system.
            config: Current configurable settings for the system.
            energy: Energy configuration and usage measurements.
        """
        self.profile = profile
        self.status = status
        self.energy = energy
        self.config = config

    def __repr__(self):
        """Return a dictionary representation of the aggregate.

        Returns:
            A dictionary containing the system identity and nested model data.
        """
        return {
            "serial": self.profile.serial,
            "name": self.profile.name,
            "profile": self.profile.__repr__(),
            "status": self.status.__repr__(),
            "config": self.config.__repr__(),
            "energy": self.energy.__repr__(),
        }

    def __str__(self):
        """Return a readable string representation of the system.

        Returns:
            The system representation converted to a string.
        """
        return str(self.__repr__())
