"""Apply Carrier realtime websocket messages to in-memory system models."""

from copy import deepcopy
from datetime import UTC, datetime
from json import loads
from logging import getLogger
from typing import Any

from deepmerge import always_merger

from .config import Config
from .status import Status
from .system import System

_LOGGER = getLogger(__name__)


def find_by_id(collection: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
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


def find_zone(
    collection: list[dict[str, Any]], zone_id: str, message_type: str
) -> dict[str, Any] | None:
    """Find a zone in a raw payload, logging and returning ``None`` when absent.

    Carrier can report a zone that was not part of the last GraphQL load, for
    example one enabled after startup. Such zones are skipped rather than
    failing the whole message.

    Args:
        collection: Raw ``zones`` list from a status or config payload.
        zone_id: Zone identifier from the websocket message.
        message_type: Message type, used only for logging.

    Returns:
        The matching zone dictionary, or ``None`` when it is not loaded.
    """
    try:
        return find_by_id(collection, zone_id)
    except ValueError:
        _LOGGER.debug("%s for unknown zone %s skipped", message_type, zone_id)
        return None


def find_activity(
    stale_activities: list[dict[str, Any]], activity: dict[str, Any]
) -> dict[str, Any] | None:
    """Find the loaded activity that a websocket activity update targets.

    Carrier does not keep activity ids unique within a zone; every activity of
    a zone can share the same id. An update is therefore matched on its
    ``type`` when it carries one, and on its ``id`` only when that id is unique
    within the zone.

    Args:
        stale_activities: Raw ``activities`` list of the loaded zone.
        activity: Activity object from an ``InfinityConfig`` message.

    Returns:
        The matching loaded activity, or ``None`` when the update names a type
        the zone does not have yet, in which case it is a new activity.

    Raises:
        ValueError: If the update matches more than one loaded activity, or
            carries no type and its id is missing or does not match exactly one
            loaded activity.
    """
    activity_type = activity.get("type")
    if activity_type is not None:
        matches = [stale for stale in stale_activities if stale.get("type") == activity_type]
        if len(matches) > 1:
            raise ValueError(f"activity type: {activity_type} is ambiguous in zone")
        return matches[0] if matches else None
    activity_id = activity.get("id")
    if activity_id is None:
        raise ValueError("activity update has neither type nor id")
    matches = [stale for stale in stale_activities if str(stale.get("id")) == str(activity_id)]
    if len(matches) != 1:
        raise ValueError(
            f"activity id: {activity_id} matches {len(matches)} activities in zone, "
            "and the update has no type"
        )
    return matches[0]


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

    def find_system(self, serial_id: str) -> System | None:
        """Return the loaded system with the requested serial number, if any.

        Args:
            serial_id: Carrier system serial number from a websocket message.

        Returns:
            The matching system object, or ``None`` when it is not loaded.
        """
        for system in self.systems:
            if system.profile.serial == serial_id:
                return system
        return None

    def carrier_system(self, serial_id: str) -> System:
        """Return the loaded system with the requested serial number.

        Args:
            serial_id: Carrier system serial number from a websocket message.

        Returns:
            The matching system object.

        Raises:
            ValueError: If no loaded system has the requested serial number.
        """
        system = self.find_system(serial_id)
        if system is not None:
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

        Messages for a device that is not loaded, and zones that are not in the
        loaded payload, are logged at debug level and skipped.

        Each message is merged into a copy of the raw payload, and the stored
        payload is only replaced once the rebuilt model parses. A message that
        fails to parse therefore raises without leaving its values behind in
        ``raw``, where they would fail every later message for that system too.

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
        system = self.find_system(serial_id)
        if system is None:
            _LOGGER.debug(
                "Received %s for unknown device %s, skipping",
                message_type or message_name,
                serial_id,
            )
            return
        match message_type or message_name:
            case "InfinityStatus":
                _LOGGER.debug("InfinityStatus received: %s", websocket_message)
                status_raw = deepcopy(system.status.raw)
                zones = websocket_message_json.pop("zones", [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    stale_zone = find_zone(status_raw["zones"], zone["id"], "InfinityStatus")
                    if stale_zone is not None:
                        always_merger.merge(stale_zone, zone)
                merged_status = always_merger.merge(status_raw, websocket_message_json)
                merged_status.update({"utcTime": datetime.now(UTC).isoformat()})
                system.status = Status(merged_status)
            case "InfinityConfig":
                _message_id = websocket_message_json.pop("id", None)
                _config_id = websocket_message_json.pop("infinitySystemConfigurationId", None)
                _LOGGER.debug("InfinityConfig received: %s", websocket_message)
                config_raw = deepcopy(system.config.raw)
                zones = websocket_message_json.pop("zones", [])
                for zone in zones:
                    _timestamp = zone.pop("timestamp", None)
                    if "id" in zone:
                        zone_id = zone["id"]
                        stale_zone = find_zone(config_raw["zones"], zone_id, "InfinityConfig")
                        if stale_zone is None:
                            continue
                        activities = zone.pop("activities", [])
                        for activity in activities:
                            _timestamp = activity.pop("timestamp", None)
                            _zone_configuration_id = activity.pop("zoneConfigurationId", None)
                            _fan_setting_id = activity.pop("fanSettingId", None)
                            # Every activity of a zone carries the zone's id, so match on type.
                            # A ValueError here rejects the whole message, leaving raw untouched.
                            stale_activity = find_activity(stale_zone["activities"], activity)
                            if stale_activity is not None:
                                always_merger.merge(stale_activity, activity)
                            else:
                                stale_zone["activities"].append(activity)
                        always_merger.merge(stale_zone, zone)
                merged_config = always_merger.merge(config_raw, websocket_message_json)
                system.config = Config(merged_config)
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
                merged_status = always_merger.merge(deepcopy(system.status.raw), status_values)
                merged_status.update({"utcTime": datetime.now(UTC).isoformat()})
                system.status = Status(merged_status)
            case _:
                _LOGGER.error("Received unknown message: %s", websocket_message)
