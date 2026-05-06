"""Carrier system profile model."""

from logging import getLogger
from typing import Any

from .util import safely_get_json_value

_LOGGER = getLogger(__name__)


class Profile:
    """Static identity and equipment metadata for a Carrier system."""

    model: str | None = None
    brand: str | None = None
    firmware: str | None = None
    indoor_model: str | None = None
    indoor_serial: str | None = None
    indoor_unit_type: str | None = None
    indoor_unit_source: str | None = None
    outdoor_model: str | None = None
    outdoor_serial: str | None = None
    outdoor_unit_type: str | None = None

    def __init__(
        self,
        raw: dict[str, Any],
    ) -> None:
        """Build a system profile from Carrier GraphQL profile data.

        Args:
            raw: Raw ``profile`` object returned by the Carrier GraphQL API.
        """
        self.raw = raw
        self.name: str = safely_get_json_value(raw, "name")
        self.serial: str = safely_get_json_value(raw, "serial")
        self.model = safely_get_json_value(self.raw, "model")
        self.brand = safely_get_json_value(self.raw, "brand")
        self.firmware = safely_get_json_value(self.raw, "firmware")
        self.indoor_model = safely_get_json_value(self.raw, "indoorModel")
        self.indoor_serial = safely_get_json_value(self.raw, "indoorSerial")
        self.indoor_unit_type = safely_get_json_value(self.raw, "idutype")
        self.indoor_unit_source = safely_get_json_value(self.raw, "idusource")
        self.outdoor_model = safely_get_json_value(self.raw, "outdoorModel")
        self.outdoor_serial = safely_get_json_value(self.raw, "outdoorSerial")
        self.outdoor_unit_type = safely_get_json_value(self.raw, "odutype")

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation suitable for logs and debugging.

        Returns:
            A dictionary containing equipment identity and model metadata.
        """
        return {
            "model": self.model,
            "brand": self.brand,
            "firmware": self.firmware,
            "indoor_model": self.indoor_model,
            "indoor_serial": self.indoor_serial,
            "indoor_unit_type": self.indoor_unit_type,
            "indoor_unit_source": self.indoor_unit_source,
            "outdoor_model": self.outdoor_model,
            "outdoor_serial": self.outdoor_serial,
            "outdoor_unit_type": self.outdoor_unit_type,
        }

    def __repr__(self) -> str:
        """Return a developer-readable representation of the profile.

        Returns:
            The profile dictionary representation converted to a string.
        """
        return str(self.as_dict())

    def __str__(self) -> str:
        """Return a readable string representation of the profile.

        Returns:
            The profile representation converted to a string.
        """
        return str(self.as_dict())
