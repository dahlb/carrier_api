import logging

import requests
from requests import Response
from requests_oauthlib import OAuth1
import xmltodict
from urllib.parse import quote

from .const import (
    INFINITY_API_BASE_URL,
    INFINITY_API_CONSUMER_KEY,
    INFINITY_API_CONSUMER_SECRET,
    FanModes,
    ActivityNames,
    HeatSourceTypes,
)
from .errors import AuthError
from .system import System

_LOGGER = logging.getLogger(__name__)


class ApiConnection:
    access_token = None

    def __init__(
        self,
        username: str,
        password: str,
    ):
        self.username = username
        self.password = password
        self.default_headers = {
            "featureset": "CONSUMER_PORTAL",
            "Accept": "application/json",
        }

    def _get(self, url: str) -> dict:
        oauth = OAuth1(
            INFINITY_API_CONSUMER_KEY,
            client_secret=INFINITY_API_CONSUMER_SECRET,
            resource_owner_key=self.username,
            resource_owner_secret=self._get_auth_token(),
            realm=url,
        )
        response = requests.get(url=url, auth=oauth, headers=self.default_headers)
        response.raise_for_status()
        return response.json()

    def _post(self, url: str, data: dict = None) -> Response:
        data_xml = None
        if data is not None:
            xml = xmltodict.unparse(data)
            data_xml = f"""data={quote(xml, safe="!~*'()")}"""
        if "users/authenticated" in url:
            resource_owner_secret = None
        else:
            resource_owner_secret = self._get_auth_token()
        oauth = OAuth1(
            INFINITY_API_CONSUMER_KEY,
            client_secret=INFINITY_API_CONSUMER_SECRET,
            resource_owner_key=self.username,
            resource_owner_secret=resource_owner_secret,
            realm=url,
        )
        response = requests.post(
            url=url, data=data_xml, auth=oauth, headers=self.default_headers
        )
        response.raise_for_status()
        return response

    def _get_auth_token(self) -> str:
        if self.access_token is None:
            url = f"{INFINITY_API_BASE_URL}/users/authenticated"
            creds = {
                "credentials": {
                    "username": self.username,
                    "password": self.password,
                },
            }
            response = self._post(url, data=creds)
            response_json = response.json()
            if "error" in response_json:
                _LOGGER.debug(response.content)
                raise AuthError(response_json["error"]["message"])
            self.access_token = response.json()["result"]["accessToken"]
        return self.access_token

    def activate(self):
        """request data refresh from api."""
        url = f"{INFINITY_API_BASE_URL}/users/{self.username}/activateSystems"
        self._post(url)

    def get_systems(self) -> [System]:
        url = f"{INFINITY_API_BASE_URL}/users/{self.username}/locations"
        response_json = self._get(url)
        systems = []
        for location in response_json["locations"]["location"]:
            for system in location["systems"]["system"]:
                system_obj = system["atom:link"]["$"]
                systems.append(
                    System(
                        api_connection=self,
                        serial=system_obj["href"].split("/")[-1],
                        name=system_obj["title"],
                    )
                )
        return systems

    def get_profile(self, system_serial: str) -> dict:
        url = f"{INFINITY_API_BASE_URL}/systems/{system_serial}/profile"
        return self._get(url)["system_profile"]

    def get_status(self, system_serial: str) -> dict:
        url = f"{INFINITY_API_BASE_URL}/systems/{system_serial}/status"
        return self._get(url)["status"]

    def get_config(self, system_serial: str) -> dict:
        url = f"{INFINITY_API_BASE_URL}/systems/{system_serial}/config"
        return self._get(url)["config"]

    def update_config(self, system_serial: str, data: dict):
        url = f"{INFINITY_API_BASE_URL}/systems/{system_serial}/config"
        self._post(url=url, data=data)

    def set_config_mode(self, system_serial: str, mode: str):
        data = {"config": {"mode": mode}}
        self.update_config(system_serial=system_serial, data=data)

    def set_heat_source(self, system_serial: str, heat_source: HeatSourceTypes):
        if heat_source not in HeatSourceTypes:
            raise ValueError(f"{heat_source} is not a valid heat source")
        data = {"config": {"heatsource": heat_source.value}}
        self.update_config(system_serial=system_serial, data=data)

    def set_config_hold(
        self,
        system_serial: str,
        zone_id: str,
        activity_name: ActivityNames,
        hold_until: str = None,
    ):
        data = {
            "config": {
                "zones": {
                    "zone": [
                        {
                            "@id": zone_id,
                            "hold": "on",
                            "holdActivity": activity_name.value,
                            "otmr": hold_until,
                        }
                    ]
                }
            }
        }
        self.update_config(system_serial=system_serial, data=data)

    def resume_schedule(self, system_serial: str, zone_id: str):
        data = {
            "config": {
                "zones": {
                    "zone": [
                        {
                            "@id": zone_id,
                            "hold": "off",
                            "holdActivity": None,
                            "otmr": None,
                        }
                    ]
                }
            }
        }
        self.update_config(system_serial=system_serial, data=data)

    def set_config_manual_activity(
        self,
        system_serial: str,
        zone_id: str,
        heat_set_point: int,
        cool_set_point: int,
        fan_mode: FanModes,
        hold_until: str = None
    ):
        data = {
            "config": {
                "zones": {
                    "zone": [
                        {
                            "@id": zone_id,
                            "hold": "on",
                            "holdActivity": ActivityNames.MANUAL.value,
                            "otmr": hold_until,
                            "activities": {
                                "activity": [
                                    {
                                        "@id": "manual",
                                        "htsp": float(heat_set_point),
                                        "clsp": float(cool_set_point),
                                        "fan": fan_mode.value,
                                    }
                                ]
                            },
                        }
                    ]
                }
            }
        }
        self.update_config(system_serial=system_serial, data=data)
