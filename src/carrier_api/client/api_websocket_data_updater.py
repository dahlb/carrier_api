from datetime import datetime, UTC
from json import loads
from typing import List, Dict

from deepmerge import always_merger
from logging import getLogger

from .. import System, Status, Config, Systems

_LOGGER = getLogger(__name__)


def find_by_id(collection: List[Dict], id_: str) -> Dict:
    for item in collection:
        if str(item['id']) == str(id_):
            return item
    raise ValueError("id: %s not found in list: %s", id_, collection)


class WebsocketDataUpdater:
    def __init__(
            self,
            systems: Systems,
    ):
        self.systems = systems

    def carrier_system(self, serial_id: str) -> System:
        for system in self.systems.systems:
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
                status_dict = system.status.to_dict()
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    stale_zone = find_by_id(status_dict["zones"], zone['id'])
                    always_merger.merge(stale_zone, zone)
                merged_status = always_merger.merge(status_dict, websocket_message_json)
                merged_status.update({"utcTime": datetime.now(UTC).isoformat()})
                system.status = Status.from_dict(merged_status)
            case "InfinityConfig":
                config_dict = system.status.to_dict()
                _message_id = websocket_message_json.pop("id", None)
                _config_id = websocket_message_json.pop("infinitySystemConfigurationId", None)
                _LOGGER.debug("InfinityConfig received: %s", websocket_message)
                zones = websocket_message_json.pop('zones', [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    if "id" in zone:
                        zone_id = zone['id']
                        stale_zone = find_by_id(config_dict["zones"], zone_id)
                        activities = zone.pop('activities', [])
                        for activity in activities:
                            _timestamp = activity.pop("timestamp", None)
                            _zone_configuration_id = activity.pop("zoneConfigurationId", None)
                            _fan_setting_id = activity.pop("fanSettingId", None)
                            stale_activity = find_by_id(stale_zone["activities"], activity["id"])
                            if stale_activity is not None:
                                always_merger.merge(stale_activity, activity)
                        always_merger.merge(stale_zone, zone)
                always_merger.merge(config_dict, websocket_message_json)
                system.config = Config.from_dict(config_dict)
            case _:
                _LOGGER.error("Received unknown message: %s", websocket_message)
