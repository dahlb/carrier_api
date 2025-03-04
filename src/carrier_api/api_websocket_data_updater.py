from datetime import datetime, UTC
from json import loads
from deepmerge import always_merger
from logging import getLogger
from .system import System
from .status import Status
from .config import Config

_LOGGER = getLogger(__name__)


def find_by_id(collection: list[dict], id: str) -> dict:
    for item in collection:
        if str(item['id']) == str(id):
            return item
    raise ValueError("id: %s not found in list: %s", id, collection)


class WebsocketDataUpdater:
    def __init__(
            self,
            systems: list[System],
    ):
        self.systems = systems

    def carrier_system(self, serial_id: str) -> System:
        for system in self.systems:
            if system.profile.serial == serial_id:
                return system
        raise ValueError("No carrier_system found for serial %s", serial_id)

    async def message_handler(self, websocket_message: str) -> None:
        websocket_message_json = loads(websocket_message)
        message_type = websocket_message_json.pop("messageType", None)
        serial_id = websocket_message_json.pop("deviceId", None)
        _timestamp = websocket_message_json.pop("timestamp", None)
        _updated_time = websocket_message_json.pop("updatedTime", None)
        system = self.carrier_system(serial_id=serial_id)
        if system is None:
            return
        match message_type:
            case "InfinityStatus":
                _LOGGER.debug("InfinityStatus received: %s", websocket_message)
                zones = websocket_message_json.pop('zones', [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    zone_id = zone['id']
                    stale_zone = find_by_id(system.status.raw["zones"], zone_id)
                    always_merger.merge(stale_zone, zone)
                merged_status = always_merger.merge(system.status.raw, websocket_message_json)
                merged_status.update({"utcTime": datetime.now(UTC).isoformat()})
                system.status = Status(merged_status)
            case "InfinityConfig":
                _message_id = websocket_message_json.pop("id", None)
                _config_id = websocket_message_json.pop("infinitySystemConfigurationId", None)
                _LOGGER.debug("InfinityConfig received: %s", websocket_message)
                zones = websocket_message_json.pop('zones', [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    zone_id = zone['id']
                    stale_zone = find_by_id(system.config.raw["zones"], zone_id)
                    activities = zone.pop('activities', [])
                    for activity in activities:
                        _timestamp = activity.pop("timestamp", None)
                        _zone_configuration_id = activity.pop("zoneConfigurationId", None)
                        _fan_setting_id = activity.pop("fanSettingId", None)
                        stale_activity = find_by_id(stale_zone["activities"], activity["id"])
                        if stale_activity is not None:
                            always_merger.merge(stale_activity, activity)
                    program = zone.pop('program', None)
                    if program is not None:
                        stale_program = stale_zone["program"]
                        for day in program["day"]:
                            for period in day["periods"]:
                                _timestamp = period.pop("timestamp", None)
                                _zone_configuration_id = period.pop("zoneConfigurationId", None)
                                _fan_setting_id = period.pop("fanSettingId", None)
                                _day_of_week_index = period.pop("dayOfWeekIndex", None)
                                period_id = period.pop("id", None)
                                day_id = period.pop("dayId", None)
                                stale_day = find_by_id(stale_program["days"], day_id)
                                if stale_day is not None:
                                    stale_period = None
                                    find_by_id(stale_day["period"], period_id)
                                    if stale_period is not None:
                                        always_merger.merge(stale_period, period)
                    always_merger.merge(stale_zone, zone)
                always_merger.merge(system.config.raw, websocket_message_json)
                system.config = Config(system.config.raw)
            case _:
                _LOGGER.error("Received unknown message: %s", websocket_message)
