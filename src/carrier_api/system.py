"""Aggregate model for a Carrier system and its related state."""

from logging import getLogger
from typing import Any

from .config import Config
from .energy import Energy
from .profile import Profile
from .status import Status

_LOGGER = getLogger(__name__)

HEAT_CAPABILITY_FIELDS = ("electric_heat", "gas", "hp_heat", "loop_pump", "reheat")
COOL_CAPABILITY_FIELDS = ("cooling", "loop_pump")
FAN_CAPABILITY_FIELDS = ("fan", "fan_gas")
HEAT_PROFILE_FIELDS = ("indoor_unit_source", "indoor_unit_type", "outdoor_unit_type")
COOL_PROFILE_FIELDS = ("outdoor_unit_type",)
HEAT_PROFILE_TOKENS = (
    "electric",
    "fan coil",
    "fancoil",
    "furnace",
    "gas",
    "heat",
    "hp",
)
COOL_PROFILE_TOKENS = ("ac", "cool", "hp")


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

    def supports_heat(self) -> bool:
        """Return whether the system reports heating capability.

        Returns:
            ``True`` when equipment metadata or energy configuration indicates
            the system has a heat-capable component.
        """
        return self._profile_contains_any(HEAT_PROFILE_FIELDS, HEAT_PROFILE_TOKENS) or (
            self._supports_any_energy_capability(HEAT_CAPABILITY_FIELDS)
        )

    def supports_cool(self) -> bool:
        """Return whether the system reports cooling capability.

        Returns:
            ``True`` when equipment metadata or energy configuration indicates
            the system has a cool-capable component.
        """
        return self._profile_contains_any(COOL_PROFILE_FIELDS, COOL_PROFILE_TOKENS) or (
            self._supports_any_energy_capability(COOL_CAPABILITY_FIELDS)
        )

    def supports_fan(self) -> bool:
        """Return whether the system reports fan-only capability.

        Returns:
            ``True`` when configuration or energy data indicates fan control is
            available.
        """
        return (self.config.fan_enabled is True) or (
            self._supports_any_energy_capability(FAN_CAPABILITY_FIELDS)
        )

    def supported_hvac_capabilities(self) -> dict[str, bool]:
        """Return supported heat, cool, and fan controls.

        Returns:
            A dictionary containing boolean support flags for ``heat``,
            ``cool``, and ``fan``.
        """
        return {
            "heat": self.supports_heat(),
            "cool": self.supports_cool(),
            "fan": self.supports_fan(),
        }

    def _supports_any_energy_capability(self, capability_fields: tuple[str, ...]) -> bool:
        """Return whether any named energy capability is enabled.

        Args:
            capability_fields: Energy model attribute names to inspect.

        Returns:
            ``True`` when any named capability is exactly ``True``.
        """
        return any(
            getattr(self.energy, capability_field, False) is True
            for capability_field in capability_fields
        )

    def _profile_contains_any(
        self, profile_fields: tuple[str, ...], capability_tokens: tuple[str, ...]
    ) -> bool:
        """Return whether profile equipment metadata contains capability hints.

        Args:
            profile_fields: Profile attribute names to inspect.
            capability_tokens: Case-insensitive substrings that imply support.

        Returns:
            ``True`` when any named profile field contains a capability token.
        """
        return any(
            capability_token in str(getattr(self.profile, profile_field, "")).lower()
            for profile_field in profile_fields
            for capability_token in capability_tokens
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the aggregate.

        Returns:
            A dictionary containing the system identity and nested model data.
        """
        return {
            "serial": self.profile.serial,
            "name": self.profile.name,
            "profile": self.profile.as_dict(),
            "status": self.status.as_dict(),
            "config": self.config.as_dict(self.status.zones),
            "energy": self.energy.as_dict(),
            "supported_hvac_capabilities": self.supported_hvac_capabilities(),
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the system.

        Returns:
            The system dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the system.

        Returns:
            The system representation converted to a string.
        """
        return str(self.as_dict())
