"""Constants and enumerations used by the Carrier API models and mutations."""

from enum import Enum


class SystemModes(Enum):
    """Operating modes accepted or reported by Carrier systems."""

    OFF = "off"
    COOL = "cool"
    HEAT = "heat"
    AUTO = "auto"
    FAN_ONLY = "fanonly"


class ActivityTypes(Enum):
    """Schedule and hold activity names used by Carrier zones."""

    HOME = "home"
    AWAY = "away"
    SLEEP = "sleep"
    WAKE = "wake"
    MANUAL = "manual"
    VACATION = "vacation"


class FanModes(Enum):
    """Fan speed modes accepted by zone activity updates."""

    OFF = "off"
    LOW = "low"
    MED = "med"
    HIGH = "high"


class TemperatureUnits(Enum):
    """Temperature unit symbols reported by Carrier configuration and status."""

    CELSIUS = "C"
    FAHRENHEIT = "F"


class HeatSourceTypes(Enum):
    """Heat source routing modes accepted by Carrier configuration updates."""

    IDU_ONLY = "idu only"
    ODU_ONLY = "odu only"
    SYSTEM = "system"
