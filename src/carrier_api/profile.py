import logging

from dateutil.parser import isoparse
import datetime

from .util import safely_get_json_value

_LOGGER = logging.getLogger(__name__)


class Profile:
    model: str = None
    brand: str = None
    firmware: str = None
    indoor_model: str = None
    indoor_serial: str = None
    indoor_unit_type: str = None
    indoor_unit_source: str = None
    outdoor_model: str = None
    outdoor_serial: str = None
    outdoor_unit_type: str = None
    time_stamp: datetime = None
    zone_ids: [str] = None
    raw_profile_json: dict = None

    def __init__(
        self,
        system,
    ):
        self.system = system
        self.refresh()

    def refresh(self):
        self.raw_profile_json = self.system.api_connection.get_profile(
            system_serial=self.system.serial
        )
        _LOGGER.debug(f"raw_profile_json:{self.raw_profile_json}")
        self.model = safely_get_json_value(self.raw_profile_json, "model")
        self.brand = safely_get_json_value(self.raw_profile_json, "brand")
        self.firmware = safely_get_json_value(self.raw_profile_json, "firmware")
        self.indoor_model = safely_get_json_value(self.raw_profile_json, "indoorModel")
        self.indoor_serial = safely_get_json_value(self.raw_profile_json, "indoorSerial")
        self.indoor_unit_type = safely_get_json_value(self.raw_profile_json, "idutype")
        self.indoor_unit_source = safely_get_json_value(self.raw_profile_json, "idusource")
        self.outdoor_model = safely_get_json_value(self.raw_profile_json, "outdoorModel")
        self.outdoor_serial = safely_get_json_value(self.raw_profile_json, "outdoorSerial")
        self.outdoor_unit_type = safely_get_json_value(self.raw_profile_json, "odutype")
        self.time_stamp = isoparse(safely_get_json_value(self.raw_profile_json, "timestamp"))
        self.zone_ids = []
        for zone in safely_get_json_value(self.raw_profile_json, "zones.zone"):
            if safely_get_json_value(zone, "present") == "on":
                self.zone_ids.append(safely_get_json_value(zone, "$.id"))

    def __repr__(self):
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
            "zone_ids": self.zone_ids,
        }

    def __str__(self):
        return str(self.__repr__())
