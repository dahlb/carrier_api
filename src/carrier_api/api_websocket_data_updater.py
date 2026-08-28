"""Apply Carrier realtime websocket messages to in-memory system models."""

from datetime import UTC, datetime
from json import loads
from logging import getLogger
from typing import Any

from deepmerge import always_merger

from .config import Config
from .status import Status
from .system import System

_LOGGER = getLogger(__name__)


def find_by_id(collection: list[dict], item_id: str) -> dict:
    """Find an item in a Carrier payload collection by id.

    Args:
        collection: List of dictionaries containing Carrier ``id`` fields.
        item_id: Identifier to match, compared as a string for API consistency.

    Returns:
        The matching dictionary from the collection.

    Raises:
        ValueError: If no item in the collection has the requested id.
    """
    for item in collection:
        if str(item["id"]) == str(item_id):
            return item
    raise ValueError(f"id: {item_id} not found in collection")


def unwrap_envelope(websocket_message_json: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a Carrier websocket message delivered inside a ``payload`` envelope.

    Carrier sends some realtime messages as ``{"deviceId": ..., "payload": {...}}``
    with the message body, including ``messageType``, nested under ``payload``.
    Messages that are already flat are returned unchanged.

    Args:
        websocket_message_json: Parsed websocket message.

    Returns:
        The message body to dispatch on, carrying the envelope ``deviceId``
        forward when the body does not supply one of its own.
    """
    payload = websocket_message_json.get("payload")
    if not isinstance(payload, dict):
        return websocket_message_json
    unwrapped = dict(payload)
    envelope_device_id = websocket_message_json.get("deviceId")
    if envelope_device_id is not None and unwrapped.get("deviceId") is None:
        unwrapped["deviceId"] = envelope_device_id
    return unwrapped


def diagnostic_status_values(value: dict[str, Any]) -> dict[str, Any]:
    """Build a status payload fragment from a ``diagnostic-device-info`` value.

    The diagnostic message reports system-wide readings under ``system`` and
    unit readings under ``idu`` and ``odu``. Those unit objects carry
    refrigerant and electrical readings, such as ``suctpress`` and ``linevolt``,
    that are not present in the GraphQL status payload.

    Args:
        value: The ``value`` object from a ``diagnostic-device-info`` message.

    Returns:
        A fragment shaped like a raw status payload, empty when the message
        carries no recognized sections.
    """
    status_values: dict[str, Any] = {}
    system_values = value.get("system")
    if isinstance(system_values, dict):
        status_values.update(system_values)
    for unit_key in ("idu", "odu"):
        unit_values = value.get(unit_key)
        if isinstance(unit_values, dict):
            status_values[unit_key] = unit_values
    return status_values


class WebsocketDataUpdater:
    """Merge Carrier websocket payloads into existing system model instances."""

    def __init__(
        self,
        systems: list[System],
    ) -> None:
        """Create a data updater for a set of Carrier systems.

        Args:
            systems: System objects previously loaded from the GraphQL API.
        """
        self.systems = systems

    def carrier_system(self, serial_id: str) -> System:
        """Return the loaded system with the requested serial number.

        Args:
            serial_id: Carrier system serial number from a websocket message.

        Returns:
            The matching system object.

        Raises:
            ValueError: If no loaded system has the requested serial number.
        """
        for system in self.systems:
            if system.profile.serial == serial_id:
                return system
        raise ValueError(f"No carrier_system found for serial {serial_id}")

    async def message_handler(self, websocket_message: str) -> None:
        """Apply one raw Carrier websocket message to the matching system.

        Messages wrapped in a ``payload`` envelope are unwrapped before dispatch.
        Status messages update the raw status payload, refresh its timestamp,
        and rebuild the ``Status`` model. Config messages merge zone activity and
        program changes into the raw config payload before rebuilding ``Config``.
        ``diagnostic-device-info`` messages merge their system and unit readings
        into the raw status payload.

        Args:
            websocket_message: JSON websocket message text from Carrier realtime
                updates.
        """
        websocket_message_json = unwrap_envelope(loads(websocket_message))
        message_type = websocket_message_json.pop("messageType", None)
        message_name = websocket_message_json.pop("name", None)
        serial_id = websocket_message_json.pop("deviceId", None)
        if serial_id is None:
            serial_id = websocket_message_json.pop("serial", None)
        _timestamp = websocket_message_json.pop("timestamp", None)
        _updated_time = websocket_message_json.pop("updatedTime", None)
        if serial_id is None:
            _LOGGER.debug(
                "Received message without deviceId, skipping messageType=%s", message_type
            )
            return
        system = self.carrier_system(serial_id=serial_id)
        if system is None:
            return
        match message_type or message_name:
            case "InfinityStatus":
                _LOGGER.debug("InfinityStatus received: %s", websocket_message)
                zones = websocket_message_json.pop("zones", [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    stale_zone = find_by_id(system.status.raw["zones"], zone["id"])
                    always_merger.merge(stale_zone, zone)
                merged_status = always_merger.merge(system.status.raw, websocket_message_json)
                merged_status.update({"utcTime": datetime.now(UTC).isoformat()})
                system.status = Status(merged_status)
            case "InfinityConfig":
                _message_id = websocket_message_json.pop("id", None)
                _config_id = websocket_message_json.pop("infinitySystemConfigurationId", None)
                _LOGGER.debug("InfinityConfig received: %s", websocket_message)
                zones = websocket_message_json.pop("zones", [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    if "id" in zone:
                        zone_id = zone["id"]
                        stale_zone = find_by_id(system.config.raw["zones"], zone_id)
                        activities = zone.pop("activities", [])
                        for activity in activities:
                            _timestamp = activity.pop("timestamp", None)
                            _zone_configuration_id = activity.pop("zoneConfigurationId", None)
                            _fan_setting_id = activity.pop("fanSettingId", None)
                            stale_activity = find_by_id(stale_zone["activities"], activity["id"])
                            if stale_activity is not None:
                                always_merger.merge(stale_activity, activity)
                        always_merger.merge(stale_zone, zone)
                always_merger.merge(system.config.raw, websocket_message_json)
                system.config = Config(system.config.raw)
            case "diagnostic-device-info":
                _LOGGER.debug("diagnostic-device-info received: %s", websocket_message)
                value = websocket_message_json.pop("value", None)
                if not isinstance(value, dict):
                    _LOGGER.debug("diagnostic-device-info carried no value object, skipping")
                    return
                status_values = diagnostic_status_values(value)
                if not status_values:
                    _LOGGER.debug("diagnostic-device-info carried no known sections, skipping")
                    return
                merged_status = always_merger.merge(system.status.raw, status_values)
                merged_status.update({"utcTime": datetime.now(UTC).isoformat()})
                system.status = Status(merged_status)
            case _:
                _LOGGER.error("Received unknown message: %s", websocket_message)
