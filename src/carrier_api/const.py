from enum import Enum

class SystemModes(Enum):
    OFF = "off"
    COOL = "cool"
    HEAT = "heat"
    AUTO = "auto"
    FAN_ONLY = "fanonly"


class ActivityTypes(Enum):
    HOME = "home"
    AWAY = "away"
    SLEEP = "sleep"
    WAKE = "wake"
    MANUAL = "manual"
    VACATION = "vacation"


class FanModes(Enum):
    OFF = "off"
    LOW = "low"
    MED = "med"
    HIGH = "high"


class TemperatureUnits(Enum):
    CELSIUS = "C"
    FAHRENHEIT = "F"


class HeatSourceTypes(Enum):
    IDU_ONLY = "idu only"
    ODU_ONLY = "odu only"
    SYSTEM = "system"
