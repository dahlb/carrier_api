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
        """Return whether Carrier energy data reports heating support.

        Carrier's captured profile fields do not expose typed HVAC capability
        enums, and the raw ``idutype``/``odutype`` values are free-form strings
        in the GraphQL schema. This helper intentionally uses parsed
        ``energyConfig`` flags only, so treat it as a best-effort reported
        support signal rather than an authoritative equipment/control contract.

        Returns:
            ``True`` when any parsed heating energy capability is displayable
            and enabled.
        """
        return self._supports_any_energy_capability(HEAT_CAPABILITY_FIELDS)

    def supports_cool(self) -> bool:
        """Return whether Carrier energy data reports cooling support.

        Carrier's captured profile fields do not expose typed HVAC capability
        enums, and the raw ``idutype``/``odutype`` values are free-form strings
        in the GraphQL schema. This helper intentionally uses parsed
        ``energyConfig`` flags only, so treat it as a best-effort reported
        support signal rather than an authoritative equipment/control contract.

        Returns:
            ``True`` when any parsed cooling energy capability is displayable
            and enabled.
        """
        return self._supports_any_energy_capability(COOL_CAPABILITY_FIELDS)

    def supports_fan(self) -> bool:
        """Return whether available Carrier data suggests fan support.

        Carrier does not expose a typed fan capability enum here. This helper
        treats the config fan flag as authoritative when Carrier provides it.
        Energy reporting flags are only a fallback when that flag is omitted.

        Returns:
            ``True`` when configuration or energy data suggests fan control is
            available.
        """
        if self.config.fan_enabled is not None:
            return self.config.fan_enabled
        return self._supports_any_energy_capability(FAN_CAPABILITY_FIELDS)

    def supported_hvac_capabilities(self) -> dict[str, bool]:
        """Return best-effort heat, cool, and fan support signals.

        Returns:
            A dictionary containing boolean support signals for ``heat``,
            ``cool``, and ``fan`` derived from Carrier config and energy data.
            These are not guaranteed to be authoritative control capabilities.
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
