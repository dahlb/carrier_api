"""Constants and enumerations used by the Carrier API models and mutations."""

from enum import Enum

VERSION: str = "3.9.1"


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


# Seconds between websocket keepalive frames.
WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS: float = 55
# Delay before the first websocket reconnect attempt; doubles after each
# connection that does not stay up, up to the maximum.
WEBSOCKET_RECONNECT_MIN_DELAY_SECONDS: float = 1
WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS: float = 300
# A websocket connection that stays open this long resets the reconnect delay.
WEBSOCKET_STABLE_CONNECTION_SECONDS: float = 60
# Refresh the access token this many seconds before Carrier's stated expiry so
# requests in flight do not carry a token that expires mid-request.
TOKEN_REFRESH_MARGIN_SECONDS: float = 60
