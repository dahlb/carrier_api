from enum import Enum

INFINITY_API_BASE_URL = "https://www.app-api.ing.carrier.com"
INFINITY_API_CONSUMER_KEY = "8j30j19aj103911h"
INFINITY_API_CONSUMER_SECRET = "0f5ur7d89sjv8d45"


class SystemModes(Enum):
    OFF = "off"
    COOL = "cool"
    HEAT = "heat"
    AUTO = "auto"
    FAN_ONLY = "fanonly"


class ActivityNames(Enum):
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
